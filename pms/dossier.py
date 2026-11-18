"""Deterministic evidence drafting. Public regulations never prove product performance."""
import hashlib,json,difflib,re
from copy import deepcopy
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.db.models import F
from .dossier_models import RADocument,RADocumentRevision,RADocumentValidation,RADocumentReview,RASourceImpactReview
from .dental_models import DentalDraft
from .dental_views import writing_access,documents_for,references_for
from .dental_workflow import build_snapshot,docx_export,stale_sections
from .search_history import source_access,adoption_access,draft_access
from .source_search import candidates
from .search_models import SearchEvidenceAdoption
from .market_service import require_workspace,allowed_markets,product_markets
from .services import audit

TYPES={'all':'전체 기술문서','description':'Device Description','performance':'Performance Summary','labeling':'Labeling / IFU'}
STATES={'DRAFT':'초안 작성','REVIEW_REQUIRED':'재검토 필요','REQUESTED':'검토 요청','CHANGES_REQUESTED':'수정 요청','APPROVED':'검토 완료'}
IMPACT_STATES={'REVIEW_REQUIRED':'검토 필요','IN_PROGRESS':'수정 진행','DONE':'검토 완료'}
def hashed(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def document_access(user,document):
    require_workspace(user)
    return document.country in allowed_markets(user) and product_markets(user).filter(device_id=document.project.device_id,market=document.country).exists() and writing_access(user,document.project.device,document.project.market)

def revision_access(user,revision):
    if not document_access(user,revision.document) or not draft_access(user,revision.draft):return False
    return all(source_access(user,ref) for row in revision.draft.snapshot.get('rows',[]) for ref in row.get('search_references',[]))

def visible_documents(user):
    return RADocument.objects.filter(country__in=allowed_markets(user),project__device_id__in=product_markets(user).values('device_id'),project__device__sales_markets__market=F('country')).distinct().select_related('project__device','project__template')

def selectable_adoptions(user,project):
    rows=SearchEvidenceAdoption.objects.filter(draft__project=project).select_related('draft__project__device','actor').order_by('-pk')
    return [r for r in rows if adoption_access(user,r)]

def current_source(user,original,available=None):
    available=candidates(user,include_history=True) if available is None else available
    family=lambda r:r['kind']==original['kind'] and r['document_id']==original['document_id']
    if original['kind']=='fda':
        from .fda_library_models import FDAReferenceVersion
        old=FDAReferenceVersion.objects.filter(pk=original['source_id']).first()
        ids=set(FDAReferenceVersion.objects.filter(key=old.key).values_list('pk',flat=True)) if old else set()
        family=lambda r:r['kind']=='fda' and r['source_id'] in ids
    elif original['kind']=='eu':
        from .eu_legal_models import EULegalDocument
        ids={original['document_id']}
        while True:
            children=set(EULegalDocument.objects.filter(parent_id__in=ids).values_list('pk',flat=True))
            if children<=ids:break
            ids|=children
        family=lambda r:r['kind']=='eu' and r['document_id'] in ids
    elif original['kind']=='regulation':
        from .models import RegulationDocument
        old=RegulationDocument.objects.filter(pk=original['document_id']).first()
        ids=set(RegulationDocument.objects.filter(document_number=old.document_number,issuer=old.issuer,jurisdiction=old.jurisdiction,device_id=old.device_id).values_list('pk',flat=True)) if old else set()
        family=lambda r:r['kind']=='regulation' and r['document_id'] in ids
    family_rows=[r for r in available if family(r)]
    if not family_rows:return None
    newest=max(r['source_id'] for r in family_rows)
    same=[r for r in family_rows if r['source_id']==newest and r['section']==original['section']]
    if not same:return None
    return next((r for r in same if r['ordinal']==original.get('ordinal')),same[0])

def change_for(user,original,available):
    current=current_source(user,original,available)
    pending=None
    if original['kind']=='fda':
        from .fda_library_models import FDAReferenceVersion
        old=FDAReferenceVersion.objects.get(pk=original['source_id'])
        newest=FDAReferenceVersion.objects.filter(key=old.key,pk__gt=old.pk).order_by('-pk').first()
        if newest and (not current or newest.pk>current['source_id']):pending={'title':newest.title,'version':newest.document_version,'official_url':newest.official_url,'reason':'new version text unavailable'}
    elif original['kind']=='eu':
        from .eu_legal_models import EULegalDocument
        related=EULegalDocument.objects.filter(parent_id=original['document_id'],language=original.get('language','en')).order_by('-pk').first()
        if related and (not current or current['document_id']!=related.pk):pending={'title':related.title,'version':related.celex or related.identifier,'official_url':related.official_url,'reason':'related amendment requires clause mapping'}
    if current and current['key']==original['key'] and not pending:return None
    snapshot={'before':deepcopy(original),'after':deepcopy(current)}
    # Current accessible section absent is distinct from a confirmed textual amendment.
    snapshot['pending_version']=pending
    snapshot['diff']='\n'.join(difflib.unified_diff(original['text'].splitlines(),(current or {}).get('text','').splitlines(),fromfile=original['version'],tofile=current['version'] if current else 'section unavailable',lineterm=''))
    if pending:snapshot['diff']+='\n새 판본·관련 개정 문서의 동일 조항 확인 필요: '+pending['version']+' '+pending['official_url']
    return {'fingerprint':hashed(snapshot),'snapshot':snapshot}

def impacts(user,revision):
    available=candidates(user,include_history=True);result=[]
    for row in revision.draft.snapshot['rows']:
        for ref in row.get('search_references',[]):
            change=change_for(user,ref,available)
            if change:
                event=revision.impact_events.filter(section=row['section'],fingerprint=change['fingerprint']).order_by('-pk').first()
                result.append({**change,'section':row['section'],'state':event.state if event else 'REVIEW_REQUIRED','event':event,'history':list(revision.impact_events.filter(section=row['section']).select_related('actor').order_by('-pk'))})
    return result

def version_state(revision):
    event=revision.review_events.order_by('-pk').first()
    return event.state if event else ('REVIEW_REQUIRED' if revision.number>1 else 'DRAFT')

def prepare_snapshot(project,kind,language="en"):
    snapshot=build_snapshot(project,references_for(project,documents_for(project.device,project.market)),use_ai=True)
    rows=snapshot['rows']
    if kind!='all':
        keywords={'description':('description','specification','intended','구성','설명'),'performance':('performance','testing','validation','성능','시험'),'labeling':('label','ifu','라벨')}[kind]
        rows=[r for r in rows if any(k in (r['title']+' '+r.get('draft_section','')).lower() for k in keywords)]
        if not rows:raise ValidationError('이 템플릿에 해당 문서 항목이 없습니다. 전체 기술문서를 선택하세요.')
    snapshot['rows']=rows
    spec=snapshot['specification']
    for row in rows:
        product_refs=[r for r in row['references'] if r['id'] in row['selected']]
        row['body']='Registered product: '+spec.get('product_name','')+'; Model: '+spec.get('model','')+'\nIntended use (declared, product evidence requires RA review): '+spec.get('intended_use','')
        if product_refs:row['body']+='\nProduct evidence: '+'\n'.join(r['excerpt']+' ['+r['citation']+']' for r in product_refs)
        if language=='ko-KR':
            row['body']='등록 제품: '+spec.get('product_name','')+'; 모델: '+spec.get('model','')+'\n등록 사용목적 (제품 증빙·적합성은 RA 검토 필요): '+spec.get('intended_use','')+('\n제품 증빙: '+'\n'.join(r['excerpt']+' ['+r['citation']+']' for r in product_refs) if product_refs else '')
        row['authored_paragraph']=True;row['product_model']=spec.get('model','');row['search_references']=[]
    snapshot['authoring_engine']=snapshot.get('engine','local');snapshot['submission_mapping_ready']=False
    return snapshot

@transaction.atomic
def create_document(user,project,kind,country,language,reason):
    require_workspace(user)
    if country not in allowed_markets(user) or not product_markets(user).filter(device=project.device,market=country).exists() or not writing_access(user,project.device,project.market):raise PermissionDenied
    from .market_models import EU_COUNTRIES
    if country not in ('US',*EU_COUNTRIES) or (country=='US')!=(project.market=='US') or kind not in TYPES or language not in ('en','ko-KR'):raise ValidationError('시장·문서 유형·작성 언어를 확인하세요.')
    if not reason.strip():raise ValidationError('작성 사유가 필요합니다.')
    document=RADocument.objects.create(project=project,document_type=kind,country=country,language=language,creator=user)
    snapshot=prepare_snapshot(project,kind,language)
    return save_revision(user,document,snapshot,reason,expected=0)

@transaction.atomic
def save_revision(user,document,snapshot,reason,expected):
    if not document_access(user,document):raise PermissionDenied
    # Reserve SQLite's writer before reading the optimistic version; PostgreSQL takes a row lock.
    from django.db import connection
    if connection.vendor=='sqlite':
        with connection.cursor() as c:c.execute('UPDATE pms_radocument SET id=id WHERE id=%s',[document.pk])
    else:RADocument.objects.select_for_update().get(pk=document.pk)
    latest=document.revisions.order_by('-number').first()
    if int(expected)!=(latest.number if latest else 0):raise ValidationError('다른 사용자가 새 버전을 저장했습니다. 최신 버전을 연 뒤 다시 저장하세요.')
    if latest and not revision_access(user,latest):raise PermissionDenied
    if not reason.strip() or len(reason)>2000:raise ValidationError('변경 사유를 입력하세요.')
    snapshot=deepcopy(snapshot);number=1 if latest is None else latest.number+1
    snapshot['authoring']={'document_id':document.pk,'number':number,'country':document.country,'language':document.language,'document_type':document.document_type}
    draft=DentalDraft.objects.create(project=document.project,author=user,snapshot=snapshot)
    revision=RADocumentRevision.objects.create(document=document,draft=draft,number=number,actor=user,reason=reason)
    audit(user,'RA_DOCUMENT_REVISION',revision,after={'document_id':document.pk,'version':number})
    return revision

def edited_snapshot(user,revision,data):
    snapshot=deepcopy(revision.draft.snapshot);available={r.pk:r for r in selectable_adoptions(user,revision.document.project)}
    for row in snapshot['rows']:
        key=row['section'];body=data.get('body_'+key,row.get('body',''));model=data.get('model_'+key,row.get('product_model',''))
        if not isinstance(body,str) or len(body)>12000 or not isinstance(model,str) or len(model)>100:raise ValidationError('문단 또는 모델 길이를 확인하세요.')
        row['body']=body;row['product_model']=model
        selected=data.get('refs_'+key,[])
        if isinstance(selected,str):selected=[selected] if selected else []
        if not isinstance(selected,list) or len(selected)>20:raise ValidationError('채택 근거를 최대 20개 선택하세요.')
        if any(not str(pk).isdecimal() or int(pk) not in available for pk in selected):raise PermissionDenied
        row['search_references']=[{**deepcopy(available[int(pk)].snapshot),'adoption_id':int(pk)} for pk in dict.fromkeys(selected)]
    return snapshot

def findings_for(user,revision):
    snapshot=revision.draft.snapshot;available=candidates(user,include_history=True);bykey={r['key']:r for r in available};findings=[]
    def add(section,code,message,severity='ERROR'):findings.append({'section':section,'code':code,'message':message,'severity':severity,'anchor':'section-'+section})
    for field in ('product_name','model','intended_use'):
        if not snapshot['specification'].get(field):add(snapshot['rows'][0]['section'],'MISSING_PRODUCT','추가 입력 필요: '+field)
    for row in snapshot['rows']:
        key=row['section']
        if not row.get('body','').strip():add(key,'MISSING_BODY','추가 입력 필요: 문단 본문')
        if row.get('product_model')!=snapshot['specification'].get('model'):add(key,'MODEL_MISMATCH','문단의 대상 모델과 제품 정보가 다릅니다.')
        declared=re.search(r'(?im)(?:^|[; ])(?:Model|모델):\s*([^\n;]+)',row.get('body',''))
        if declared and declared[1].strip()!=snapshot['specification'].get('model'):add(key,'BODY_MODEL_MISMATCH','본문의 Model 값과 작성 대상 모델이 다릅니다.')
        if not row.get('search_references'):add(key,'MISSING_REGULATORY_EVIDENCE','추가 입력 필요: 이 항목의 규정 근거를 채택하세요.','REVIEW')
        for ref in row.get('search_references',[]):
            actual=bykey.get(ref['key'])
            if not actual or actual['text']!=ref['text'] or actual['section']!=ref['section'] or actual['version']!=ref['version'] or actual['official_url']!=ref['official_url']:
                add(key,'INVALID_CITATION','인용 조항·발췌·버전·공식 URL이 보존 원문과 일치하지 않습니다.')
            if change_for(user,ref,available):add(key,'SOURCE_CHANGED','근거 버전 또는 조항이 변경됐습니다. 원문 영향 검토가 필요합니다.','REVIEW')
        for gap in row.get('gaps',[]):add(key,'PRODUCT_EVIDENCE_NEEDED',str(gap),'REVIEW')
        add(key,'CONTENT_REVIEW','규정의 적용 범위와 제품 주장·시험 근거의 적합성을 담당자가 확인하세요.','REVIEW')
    for section in stale_sections(revision.document.project,snapshot,documents_for(revision.document.project.device,revision.document.project.market)):
        add(section,'PRODUCT_EVIDENCE_CHANGED','제품·템플릿 또는 제품 증빙 버전이 변경됐습니다. RA 재검토가 필요합니다.','REVIEW')
    if snapshot['specification']!=revision.document.project.specification:
        add(snapshot['rows'][0]['section'],'PRODUCT_CHANGED','작성 당시 제품 정보와 현재 프로젝트 정보가 다릅니다.','REVIEW')
    context={'project_specification':deepcopy(revision.document.project.specification),'source_keys':sorted(r['key'] for r in available),'impacts':[{'section':i['section'],'fingerprint':i['fingerprint'],'state':i['state']} for i in impacts(user,revision)]}
    return findings,context

@transaction.atomic
def validate(user,revision):
    if not revision_access(user,revision):raise PermissionDenied
    findings,context=findings_for(user,revision)
    result=RADocumentValidation.objects.create(revision=revision,actor=user,fingerprint=hashed([revision.draft.snapshot,findings,context]),findings=findings,context=context)
    audit(user,'RA_DOCUMENT_VALIDATE',result,after={'revision_id':revision.pk,'errors':sum(r['severity']=='ERROR' for r in findings)})
    return result

@transaction.atomic
def review(user,revision,state,reason,expected,acknowledged=False):
    if not revision_access(user,revision):raise PermissionDenied
    from django.db import connection
    if connection.vendor=='sqlite':
        with connection.cursor() as cursor:cursor.execute('UPDATE pms_radocument SET id=id WHERE id=%s',[revision.document_id])
    else:RADocument.objects.select_for_update().get(pk=revision.document_id)
    latest=revision.document.revisions.order_by('-number').first()
    if latest.pk!=revision.pk:raise ValidationError('이전 버전의 검토 상태는 변경할 수 없습니다. 최신 버전을 여세요.')
    current=revision.review_events.order_by('-pk').first()
    if int(expected)!=(current.pk if current else 0):raise ValidationError('검토 상태가 변경됐습니다. 최신 이력을 확인하세요.')
    allowed={'DRAFT':('REQUESTED',),'REVIEW_REQUIRED':('REQUESTED',),'REQUESTED':('CHANGES_REQUESTED','APPROVED'),'CHANGES_REQUESTED':('REQUESTED',),'APPROVED':()}
    if state not in allowed[version_state(revision)] or not reason.strip() or len(reason)>2000:raise ValidationError('검토 단계와 변경 사유를 확인하세요.')
    validation=revision.validations.order_by('-pk').first()
    if state in ('REQUESTED','APPROVED'):
        findings,context=findings_for(user,revision)
        if not validation or validation.fingerprint!=hashed([revision.draft.snapshot,findings,context]):raise ValidationError('현재 내용·근거로 다시 검증한 후 요청하세요.')
        if state=='APPROVED' and (any(r['severity']=='ERROR' for r in findings) or not acknowledged or any(i['state']!='DONE' for i in impacts(user,revision))):raise ValidationError('검증 오류·변경 근거를 해결하고 담당자 적합성 검토를 확인하세요.')
    event=RADocumentReview.objects.create(revision=revision,actor=user,state=state,reason=reason,validation=validation)
    # Preserve the existing writing review entry point as well.
    if state=='APPROVED':revision.draft.reviews.create(reviewer=user,note='RA document review: '+reason)
    audit(user,'RA_DOCUMENT_REVIEW',event,after={'revision_id':revision.pk,'state':state})
    return event

def export_docx(user,revision):
    snapshot=deepcopy(revision.draft.snapshot)
    for row in snapshot['rows']:row['authored_paragraph']=True
    state=effective_state(user,revision)
    snapshot['template']['name']+=' | Document v'+str(revision.number)+' | '+state+' | '+revision.document.language
    return docx_export(snapshot)

def effective_state(user,revision):
    state=version_state(revision)
    if state=='APPROVED' and (any(i['state']!='DONE' for i in impacts(user,revision)) or revision.draft.snapshot['specification']!=revision.document.project.specification):return 'REVIEW_REQUIRED'
    return state
