import json,time,hashlib
from contextlib import ExitStack
from unittest.mock import patch
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from django.conf import settings
from pms.source_search import search,candidates
from pms.fda_library_models import FDAReferenceVersion
from pms.search_models import EULegalTextVersion


class Command(BaseCommand):
    help='Run predeclared Korean questions on the identical authorized corpus and report hit@5.'
    def add_arguments(self,parser):
        parser.add_argument('--user',required=True)
        parser.add_argument('--cases',default=str(Path(__file__).resolve().parents[2]/'search_evaluation.json'))
        parser.add_argument('--output',required=True)
        parser.add_argument('--verify-offline',action='store_true',help='Block outgoing socket connections during every search.')
        parser.add_argument('--baseline',help='Preserved previous evaluation; questions and judgements must match exactly.')
        parser.add_argument('--language',default='')
    def handle(self,**options):
        user=get_user_model().objects.get(username=options['user'])
        cases=json.loads(Path(options['cases']).read_text(encoding='utf-8'))
        baseline=json.loads(Path(options['baseline']).read_text(encoding='utf-8')) if options.get('baseline') else None
        if baseline and [{k:q[k] for k in ('id','query','jurisdiction','relevant')} for q in baseline['results']]!=cases['questions']:
            raise CommandError('평가 질문 또는 사전 지정 정답이 변경됐습니다.')
        fda=dict(FDAReferenceVersion.objects.values_list('pk','key'))
        eu=dict(EULegalTextVersion.objects.values_list('pk','document__celex'))
        def relevant(row,expected):
            if row['kind']!=expected['kind']:return False
            if row['kind']=='fda':return fda.get(row['source_id'])==expected['key'] and row['page'] in expected['pages']
            return eu.get(row['source_id'])==expected['celex'] and row['section']==expected['section']
        results=[]
        for question in cases['questions']:
            filters={'jurisdiction':question['jurisdiction'],'language':options['language']}
            rows=candidates(user,**filters)
            fingerprint=lambda values:hashlib.sha256(json.dumps(sorted(row['key'] for row in values)).encode()).hexdigest()
            corpus_hash=fingerprint(rows)
            eligible=any(relevant(row,question['relevant']) for row in rows)
            item={**question,'eligible':eligible,'reason':'' if eligible else '관련 조항 본문이 저장돼 있지 않아 평가 불가','filters':filters,'corpus_hash':corpus_hash,'runs':{}}
            for mode in ('keyword','ai','ai_rerank'):
                if fingerprint(candidates(user,**filters))!=corpus_hash:raise CommandError('평가 도중 문서 집합이 변경됐습니다. 같은 집합에서 다시 실행하세요.')
                start=time.perf_counter()
                with ExitStack() as stack:
                    if options['verify_offline']:
                        stack.enter_context(patch('socket.socket.connect',side_effect=RuntimeError('Offline validation: outbound connection blocked')))
                        stack.enter_context(patch('socket.create_connection',side_effect=RuntimeError('Offline validation: outbound connection blocked')))
                    # Only the original question and public scope filters enter retrieval. Never the relevance labels.
                    result=search(user,question['query'],mode=mode,rerank=False if mode=='ai' else None,**filters)
                hit=any(relevant(row,question['relevant']) for row in result['results']) if eligible else None
                item['runs'][mode]={'engine':result['engine'],'fallback_reason':result['fallback_reason'],'reranker_reason':result['reranker_reason'],
                    'model_id':result['model_id'],'revision':result['revision'],'device':result['device'],
                    'reranker_applied':result['reranker_applied'],'reranker_id':result['reranker_id'],'reranker_revision':result['reranker_revision'],
                    'rerank_trace':result['rerank_trace'],'rerank_execution':result['rerank_execution'],
                    'status':'not_evaluable' if not eligible else 'hit' if hit else 'miss',
                    'hit_at_5':hit,
                    'elapsed_seconds':round(time.perf_counter()-start,3),
                    'results':[{k:row.get(k) for k in ('kind','source_id','title','version','section','page','official_url','text','key','language','collected_at','relevance_score','score_type')} for row in result['results']]}
            results.append(item)
        count=sum(item['eligible'] for item in results)
        summary={'schema':1,'model_id':settings.SOURCE_SEARCH_MODEL_ID,'revision':settings.SOURCE_SEARCH_REVISION,
            'profile':f'cls-l2:v1:{settings.SOURCE_SEARCH_MAX_TOKENS}','reranker_enabled':settings.SOURCE_SEARCH_RERANKER_ENABLED,
            'questions':len(results),'eligible_questions':count,'coverage':count/len(results),'outbound_connections_blocked':options['verify_offline'],'results':results,'metrics':{}}
        summary['cases_sha256']=hashlib.sha256(Path(options['cases']).read_bytes()).hexdigest()
        summary['baseline_metrics']=baseline['metrics'] if baseline else None
        summary['device']=settings.SOURCE_SEARCH_DEVICE;summary['reranker_id']=settings.SOURCE_SEARCH_RERANKER_ID;summary['reranker_revision']=settings.SOURCE_SEARCH_RERANKER_REVISION
        for mode in ('keyword','ai','ai_rerank'):
            hits=sum(item['runs'][mode]['hit_at_5'] is True for item in results)
            actual_engines=sorted({item['runs'][mode]['engine'] for item in results if item['eligible']})
            fda=[item for item in results if item['jurisdiction']=='US' and item['eligible']]
            summary['metrics'][mode]={'hits':hits,'denominator':count,'hit_at_5':hits/count if count else None,'actual_engines':actual_engines,
                'fda_hits':sum(item['runs'][mode]['hit_at_5'] is True for item in fda),'fda_questions':len(fda),
                'requested_engine_verified':all(item['runs'][mode]['engine']=={'keyword':'keyword','ai':'hybrid_rrf','ai_rerank':'hybrid_rrf_reranked'}[mode] for item in results if item['eligible'])}
        Path(options['output']).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps({k:v for k,v in summary.items() if k!='results'},ensure_ascii=False,indent=2))
