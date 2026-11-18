"""Authorized read-only source retrieval: local dense + existing lexical ranks, fused by RRF."""
import hashlib
import json
import math
import re
from django.conf import settings
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from .market_codes import market_code
from .market_models import EU_COUNTRIES
from .market_service import require_workspace,allowed_markets,scoped,product_markets
from .models import RegulationChunk
from .regulation_documents import documents_for,tokens,keyword_rank
from .file_security import safe_attachment_bytes
from .fda_library_models import FDAReferenceVersion
from .search_models import (SourceSearchPassage,SourceSearchEmbedding,EULegalTextVersion,EUSearchHead,EUSearchRelease,SourceIndexBuild)
from django.utils import timezone
from . import local_search_models as local


def digest(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()


def split_text(text,section=''):
    # Reuse existing locations when supplied; never infer a legal obligation or date.
    positioned=re.sub(r'(?m)^(?=\s*(?:Article\s+\d+\b|[IVX]+\.\s*[A-Z]|[A-J]\.\s+[A-Z]))','\n\n',text)
    blocks=re.split(r'\n\s*\n',positioned)
    for block in blocks:
        lines=[line.strip() for line in block.splitlines() if line.strip()]
        for line in lines:
            if re.match(r'^(Article\s+\d+\b|[IVX]+\.\s+[A-Za-z]|[A-J]\.\s+[A-Za-z])',line):section=line[:240];break
        body=re.sub(r'\s+',' ',block).strip()
        # A deterministic 120-character overlap keeps paragraph boundaries traceable.
        size=max(200,min(settings.SOURCE_SEARCH_CHUNK_CHARS,1000));overlap=min(120,size//4)
        for offset in range(0,len(body),size-overlap):
            part=body[offset:offset+size]
            if len(part)>=25:yield section,part


def entry(kind,source_id,ordinal,text,title,version,section='',page=None,**metadata):
    model_text=f'{title}\n{section}\n{text}'
    fingerprint=digest(model_text)
    return dict(key=f'{kind}:{source_id}:{page or 0}:{ordinal}:{fingerprint}',kind=kind,source_id=source_id,
        ordinal=ordinal,title=title,version=version,section=section,page=page,text=text,model_text=model_text,
        content_hash=fingerprint,**metadata)


def candidates(user,jurisdiction='',edition='',document_id=None,language='',include_pending=False,include_history=False):
    require_workspace(user)
    allowed=allowed_markets(user);wanted=jurisdiction.strip().upper()
    if wanted and wanted not in ('US','EU',*EU_COUNTRIES):raise ValidationError('관할 필터를 확인하세요.')
    def permits(code):
        return (code in allowed or code=='EU' and bool(set(allowed)&set(EU_COUNTRIES))) and (not wanted or wanted==code or wanted in EU_COUNTRIES and code=='EU')
    rows=[];checked={}
    docs=documents_for(user).filter(scan_status='PASSED',extraction_status='READY')
    if scoped(user):docs=docs.filter(Q(device__isnull=True)|Q(device_id__in=product_markets(user).values('device_id')))
    if edition:docs=docs.filter(edition=edition)
    if document_id:docs=docs.filter(pk=document_id)
    for chunk in RegulationChunk.objects.filter(document__in=docs).select_related('document').order_by('pk'):
        doc=chunk.document;code=market_code(doc.jurisdiction)
        if code not in ('US','EU',*EU_COUNTRIES) or not permits(code) or language and (doc.language or 'und')!=language:continue
        if digest(chunk.text)!=chunk.content_hash:continue
        if doc.pk not in checked:
            try:safe_attachment_bytes(doc);checked[doc.pk]=True
            except (PermissionDenied,OSError,ValueError):checked[doc.pk]=False
        if not checked[doc.pk]:continue
        rows.append(entry('regulation',chunk.pk,0,chunk.text,doc.title,doc.edition,chunk.section,chunk.page,
            jurisdiction=code,document_id=doc.pk,document_type='미확인',official_url=doc.official_url,
            location_url=reverse('market-source-document',args=[doc.pk])+f'?chunk={chunk.pk}#chunk-{chunk.pk}',
            effective_on=str(doc.effective_on or ''),parent_hash=doc.sha256,is_example=doc.is_example,language=doc.language or 'und',collected_at=doc.created_at.isoformat()))
    if not document_id and permits('US'):
        for source in FDAReferenceVersion.objects.filter(retrieval_status='verified_text').order_by('pk'):
            source_language=source.metadata.get('language','en')
            if language and language!=source_language:continue
            if edition and edition not in (source.document_version,f'v{source.version}'):continue
            parent_hash=digest(json.dumps(source.pages,sort_keys=True,ensure_ascii=False))
            for page,body in sorted(source.pages.items(),key=lambda pair:int(pair[0])):
                number=int(page)
                headings=[s for s in source.sections if s.get('page',0)<=number]
                heading=max(headings,key=lambda s:s.get('page',0)).get('clause','') if headings else ''
                for ordinal,(section,text) in enumerate(split_text(body,heading)):
                    rows.append(entry('fda',source.pk,ordinal,text,source.title,source.document_version,section,number,
                        jurisdiction='US',document_id=source.pk,document_type=source.source_type,
                        official_url=(source.pdf_url+f'#page={number}') if source.pdf_url else source.official_url,
                        location_url=reverse('market-fda-source',args=[source.pk]),effective_on='',parent_hash=parent_hash,
                        is_example=False,language=source_language,collected_at=source.recorded_at.isoformat()))
    if not document_id and permits('EU'):
        versions=EULegalTextVersion.objects.select_related('document').order_by('pk')
        if include_pending:
            # One latest staged text per legal document, plus the current head on failure.
            latest={row.document_id:row.pk for row in versions}
            versions=versions.filter(pk__in=latest.values())
        elif edition or include_history:versions=versions.filter(pk__in=EUSearchRelease.objects.values('text_version_id'))
        else:versions=versions.filter(pk__in=EUSearchHead.objects.exclude(active_text=None).values('active_text_id'))
        for source in versions:
            doc=source.document;version=f'{doc.celex or doc.identifier} · text-v{source.version} · {doc.language}'
            if language and doc.language!=language:continue
            if edition and edition not in (version,doc.identifier,f'text-v{source.version}'):continue
            if digest(source.text)!=source.content_hash:continue
            if source.sections and '\n\n'.join(group['text'] for group in source.sections)!=source.text:continue
            index=0
            for group in source.sections or [{'section':'','text':source.text,'anchor':''}]:
                for ordinal,(section,text) in enumerate(split_text(group['text'],group['section'])):
                    # Separate articles use a unique stable ordinal across the saved text version.
                    page=group.get('page');url=source.resolved_url or source.official_url
                    url+=f'#page={page}' if page else (('#'+group['anchor']) if group.get('anchor') else '')
                    rows.append(entry('eu',source.pk,index,text,doc.title,version,section,page,
                        jurisdiction='EU',document_id=doc.pk,document_type=doc.kind,official_url=url,
                        location_url=reverse('market-search-eu-text',args=[source.pk]),effective_on=str(doc.effective_on or ''),
                        parent_hash=source.content_hash,is_example=False,coverage=source.scope_description,language=doc.language,
                        collected_at=source.retrieved_at.isoformat(),canonical_url=source.official_url,source_method=source.source_method))
                    index+=1
    if len(rows)>settings.SOURCE_SEARCH_MAX_PASSAGES:raise ValidationError('검색 범위가 큽니다. 관할·문서 버전 필터로 좁히세요.')
    return rows


def sync_passages(rows):
    """Index maintenance only; old source and passage versions are never overwritten."""
    saved=[];created_count=0
    for row in rows:
        source_field={'regulation':'regulation_chunk_id','fda':'fda_reference_id','eu':'eu_text_id'}[row['kind']]
        passage,created=SourceSearchPassage.objects.get_or_create(key=row['key'],defaults={source_field:row['source_id'],
            'section':row['section'],'page':row['page'],'ordinal':row['ordinal'],'text':row['text'],
            'content_hash':row['content_hash'],'parent_hash':row['parent_hash']})
        saved.append((passage,row));created_count+=created
    return saved,created_count


def index_sources(user,lexical_only=False,**filters):
    rows=candidates(user,include_pending=True,**filters);saved,created=sync_passages(rows)
    result=dict(passages=len(rows),created=created,embedded=0,unchanged=0)
    if lexical_only:return result
    model_id,revision=local.identity();profile=local.profile()
    pending=[]
    for passage,row in saved:
        value=passage.embeddings.filter(model_id=model_id,revision=revision,profile=profile,content_hash=row['content_hash']).first()
        if value and local.valid_vector(value.vector,value.dimension):result['unchanged']+=1
        else:pending.append((passage,row))
    build=SourceIndexBuild.objects.create(actor=user)
    try:
        model=local.load() if pending else None;batch=max(1,min(settings.SOURCE_SEARCH_BATCH_SIZE,16))
        for offset in range(0,len(pending),batch):
            items=pending[offset:offset+batch]
            vectors=model.encode([row['model_text'] for _,row in items])
            if len(vectors)!=len(items) or any(not local.valid_vector(vector) for vector in vectors):raise ValidationError('임베딩 결과가 유효하지 않습니다.')
            with transaction.atomic():
                for (passage,row),vector in zip(items,vectors):
                    SourceSearchEmbedding.objects.update_or_create(passage=passage,model_id=model_id,revision=revision,profile=profile,
                        defaults={'vector':vector,'dimension':len(vector),'content_hash':row['content_hash']})
                    result['embedded']+=1
        result['activated']=publish_eu(rows,model_id,revision,profile)
        build.state='READY'
    except BaseException as exc:
        build.state='FAILED';build.failure=type(exc).__name__;raise
    finally:
        build.finished_at=timezone.now();build.counts=result;build.save()
    return result


def publish_eu(rows,model_id,revision,profile):
    from .eu_acquisition import lock_document
    activated=0
    for pk in sorted({row['source_id'] for row in rows if row['kind']=='eu'}):
        text=EULegalTextVersion.objects.select_related('document').get(pk=pk)
        selected=[row for row in rows if row['kind']=='eu' and row['source_id']==pk]
        with transaction.atomic():
            lock_document(text.document)
            newest=EULegalTextVersion.objects.filter(document=text.document).order_by('-version').first()
            if newest.pk!=pk:continue # A newer import arrived while the model was running.
            stored=list(SourceSearchEmbedding.objects.filter(passage__key__in=[row['key'] for row in selected],model_id=model_id,revision=revision,profile=profile).select_related('passage'))
            expected={row['key']:row['content_hash'] for row in selected}
            if len(stored)!=len(selected) or any(not local.valid_vector(v.vector,v.dimension) or v.content_hash!=expected[v.passage.key] or v.passage.parent_hash!=text.content_hash for v in stored):
                raise ValidationError('불완전한 EU 색인은 게시하지 않습니다.')
            EUSearchRelease.objects.get_or_create(text_version=text,model_id=model_id,revision=revision,profile=profile,defaults={'passage_count':len(selected)})
            head,_=EUSearchHead.objects.get_or_create(document=text.document)
            if head.active_text_id!=pk:
                head.active_text=text;head.published_at=timezone.now();head.save();activated+=1
    return activated


def rrf(*rankings,k=60):
    scores={}
    for ranking in rankings:
        for position,key in enumerate(dict.fromkeys(ranking),1):scores[key]=scores.get(key,0)+1/(k+position)
    return sorted(scores,key=lambda key:(-scores[key],key))


def search(user,query,mode='ai',limit=5,rerank=None,**filters):
    require_workspace(user)
    if not isinstance(query,str) or not query.strip() or len(query)>300:raise ValidationError('1~300자의 검색 질문을 입력하세요.')
    if mode not in ('ai','keyword','ai_rerank'):raise ValidationError('검색 방식을 확인하세요.')
    if not 1<=limit<=20:raise ValidationError('검색 결과 수는 1~20개입니다.')
    rows=candidates(user,**filters);lookup={row['key']:row for row in rows}
    lexical=[row['key'] for _,row in keyword_rank(query,[(row,tokens(row['model_text'])) for row in rows])]
    keys=lexical;engine='keyword';reason='';reranker_reason='';model_id='';revision=''
    trace=[];rerank_info={};reranker_id='';reranker_revision='';applied=False;rank_scores={};score_type='keyword relevance'
    if mode!='keyword' and rows:
        try:
            model_id,revision=local.identity()
            embeddings={value.passage.key:value for value in SourceSearchEmbedding.objects.filter(
                passage__key__in=lookup,model_id=model_id,revision=revision,profile=local.profile()).select_related('passage')}
            if len(embeddings)!=len(rows):raise local.ModelUnavailable('index_missing_or_stale')
            for key,value in embeddings.items():
                if value.content_hash!=lookup[key]['content_hash'] or value.passage.parent_hash!=lookup[key]['parent_hash'] or not local.valid_vector(value.vector,value.dimension):
                    raise local.ModelUnavailable('index_invalid')
            vector=local.load().encode([query])[0]
            if not local.valid_vector(vector):raise local.ModelUnavailable('query_embedding_invalid')
            if any(value.dimension!=len(vector) for value in embeddings.values()):raise local.ModelUnavailable('index_invalid')
            dense=sorted(lookup,key=lambda key:(-sum(a*b for a,b in zip(vector,embeddings[key].vector)),key))[:50]
            keys=rrf(lexical[:50],dense);engine='hybrid_rrf';score_type='RRF relevance'
            for ranking in (lexical[:50],dense):
                for rank,key in enumerate(ranking,1):rank_scores[key]=rank_scores.get(key,0)+1/(60+rank)
        except local.ModelUnavailable as exc:reason=str(exc)
        except (RuntimeError,ValueError,ImportError,OSError):reason='model_inference_failed'
        wanted=mode=='ai_rerank' or (mode=='ai' and (settings.SOURCE_SEARCH_RERANKER_ENABLED if rerank is None else rerank))
        if engine=='hybrid_rrf' and wanted and not settings.SOURCE_SEARCH_RERANKER_ENABLED:reranker_reason='reranker_disabled'
        if engine=='hybrid_rrf' and wanted and settings.SOURCE_SEARCH_RERANKER_ENABLED:
            before=keys[:20];scores=None
            try:
                reranker_id,reranker_revision=local.identity(True)
                shortlist=keys[:20];reranker=local.load(reranker=True);texts=[lookup[key]['model_text'] for key in shortlist]
                if hasattr(reranker,'rerank_with_info'):scores,rerank_info=reranker.rerank_with_info(query,texts)
                else:scores=reranker.rerank(query,texts)
                if len(scores)!=len(shortlist) or any(not math.isfinite(s) for s in scores):raise ValueError()
                keys=[key for _,key in sorted(zip(scores,shortlist),key=lambda row:(-row[0],row[1]))];engine='hybrid_rrf_reranked';applied=True
                rank_scores=dict(zip(shortlist,scores));score_type='reranker logit relevance (not probability)'
            except (local.ModelUnavailable,RuntimeError,ValueError,ImportError,OSError):reranker_reason='reranker_unavailable'
            trace=[{'key':key,'before':rank+1,'after':keys.index(key)+1,'score':rank_scores.get(key),'applied':applied} for rank,key in enumerate(before)]
    elif mode!='keyword':reason='no_accessible_source_text'
    if engine=='keyword':rank_scores={row['key']:score for score,row in keyword_rank(query,[(row,tokens(row['model_text'])) for row in rows])}
    output=[{**lookup[key],'relevance_score':round(rank_scores.get(key,0),6),'score_type':score_type} for key in keys[:limit]]
    return dict(requested_mode=mode,engine=engine,fallback_reason=reason,reranker_reason=reranker_reason,device=settings.SOURCE_SEARCH_DEVICE if engine!='keyword' else '',
        model_id=model_id if engine!='keyword' else '',revision=revision if engine!='keyword' else '',
        reranker_applied=applied,reranker_id=reranker_id if applied else '',reranker_revision=reranker_revision if applied else '',rerank_trace=trace,
        rerank_execution=rerank_info if applied else {},
        results=output,candidate_count=len(rows),external_inference=False)
