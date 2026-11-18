from django import forms
from django.core.exceptions import ValidationError
from django.http import JsonResponse,Http404,FileResponse
from django.shortcuts import render,get_object_or_404
from django.core.paginator import Paginator
from io import BytesIO
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from .market_views import market_view
from .market_service import allowed_markets,scoped,product_markets
from .market_models import EU_COUNTRIES
from .market_codes import market_code
from .regulation_documents import documents_for
from .file_security import safe_attachment_bytes
from .source_search import search,digest

REASONS={
    'index_missing_or_stale':'현재 모델·리비전의 색인이 없거나 문서가 추가됐습니다. 색인을 생성·갱신하세요.',
    'index_invalid':'색인 벡터 또는 원문 해시가 유효하지 않습니다. 색인을 다시 확인하세요.',
    'model_not_cached':'고정 리비전 모델이 로컬 캐시에 없습니다. 모델 준비 명령을 실행하세요.',
    'model_load_failed':'로컬 모델 또는 선택 패키지를 불러올 수 없습니다. 설치·캐시·메모리를 확인하세요.',
    'model_revision_invalid':'모델 ID와 고정 커밋 SHA 설정을 확인하세요.',
    'model_inference_failed':'로컬 모델 계산에 실패했습니다. 키워드 검색으로 실행했습니다.',
    'query_embedding_invalid':'질의 임베딩이 유효하지 않아 키워드 검색으로 실행했습니다.',
    'no_accessible_source_text':'접근 가능한 색인 대상 본문이 없습니다. 링크만 등록한 문서는 본문 수집 후 검색할 수 있습니다.',
    'reranker_unavailable':'재정렬 모델을 사용할 수 없어 RRF 순위를 유지했습니다.',
    'reranker_disabled':'재정렬은 운영 설정에서 비활성입니다. RRF 순위를 유지했습니다.',
    'device_unavailable':'설정한 실행 장치를 사용할 수 없어 키워드 검색으로 전환했습니다.',
    'token_budget_exceeded':'토큰 예산을 초과했습니다. 잘라서 처리하지 않았습니다. 질문을 줄이거나 더 작은 구간으로 다시 색인하세요.'}

class SearchForm(forms.Form):
    query=forms.CharField(label='한국어 질문 / 식별자',max_length=300)
    mode=forms.ChoiceField(label='검색 방식',choices=[('keyword','키워드'),('ai','키워드 + 의미 검색'),('ai_rerank','키워드 + 의미 검색 + 재정렬')],initial='ai')
    language=forms.ChoiceField(label='원문 언어',required=False,choices=[('','전체'),('en','English'),('ko','한국어'),('de','Deutsch'),('fr','Français'),('es','Español'),('it','Italiano'),('und','미확인')])
    jurisdiction=forms.ChoiceField(label='관할',required=False)
    edition=forms.CharField(label='문서 버전 (비우면 모든 보존 버전)',max_length=160,required=False)
    document_id=forms.IntegerField(label='업로드 규정 문서 ID (선택)',min_value=1,required=False)
    limit=forms.IntegerField(label='결과 수',min_value=1,max_value=20,initial=5,required=False)
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        markets=allowed_markets(user)
        choices=[('','허용된 관할 전체')]
        if 'US' in markets:choices.append(('US','미국 FDA'))
        if set(markets)&set(EU_COUNTRIES):choices.append(('EU','유럽연합 EU'))
        choices.extend((code,code) for code in EU_COUNTRIES if code in markets)
        self.fields['jurisdiction'].choices=choices

@market_view
@never_cache
@require_GET
def source_search(request,api=False):
    data=request.GET.copy()
    if 'mode' not in data:data['mode']='ai'
    form=SearchForm(data if request.GET or api else None,user=request.user)
    result=None;status=200
    if request.GET or api:
        if form.is_valid():
            values=dict(form.cleaned_data);values['limit']=values['limit'] or 5
            try:
                result=search(request.user,rerank=False if values['mode']=='ai' else None,**values)
                from .search_history import record_execution
                event=record_execution(request.user,values['query'],{key:values[key] for key in ('jurisdiction','edition','document_id','language')},result)
                result['execution_id']=event.pk
            except ValidationError as exc:form.add_error(None,exc);status=400
        else:status=400
    if api:
        if result is None:return JsonResponse({'errors':form.errors.get_json_data()},status=400)
        result['results']=[{key:value for key,value in row.items() if key not in ('model_text','parent_hash')} for row in result['results']]
        return JsonResponse(result,json_dumps_params={'ensure_ascii':False})
    reason=REASONS.get(result['fallback_reason'],'') if result else ''
    reranker_reason=REASONS.get(result['reranker_reason'],'') if result else ''
    markets=allowed_markets(request.user)
    from .eu_legal_models import EULegalDocument
    from .search_models import EUSearchHead
    eu_status=[]
    if set(markets)&set(EU_COUNTRIES):
        for doc in EULegalDocument.objects.all():
            head=EUSearchHead.objects.filter(document=doc).select_related('active_text').first()
            eu_status.append({'document':doc,'head':head,'success':doc.source_attempts.filter(status='SUCCESS').order_by('-pk').first()})
    return render(request,'pms/markets/source_search.html',dict(form=form,result=result,reason=reason,reranker_reason=reranker_reason,eu_status=eu_status,
        us_access='US' in markets,eu_access=bool(set(markets)&set(EU_COUNTRIES)),source_search_local_only=True),status=status)

@market_view
@never_cache
@require_GET
def source_document(request,pk,download=False):
    doc=get_object_or_404(documents_for(request.user),pk=pk,scan_status='PASSED',extraction_status='READY')
    code=market_code(doc.jurisdiction);markets=allowed_markets(request.user)
    if not(code in ('US','EU',*EU_COUNTRIES) and (code in markets or code=='EU' and set(markets)&set(EU_COUNTRIES))):raise Http404
    if doc.device_id and scoped(request.user) and not product_markets(request.user).filter(device_id=doc.device_id).exists():raise Http404
    raw=safe_attachment_bytes(doc)
    if download:
        response=FileResponse(BytesIO(raw),as_attachment=True,filename=doc.original_name)
        response['Content-Security-Policy']="sandbox; default-src 'none'"
        return response
    chunks=[chunk for chunk in doc.chunks.all() if digest(chunk.text)==chunk.content_hash]
    paginator=Paginator(chunks,20);number=request.GET.get('p',1);selected=request.GET.get('chunk')
    for index,chunk in enumerate(chunks):
        if str(chunk.pk)==selected:number=index//20+1;break
    return render(request,'pms/regulatory/document_detail.html',dict(item=doc,chunks=paginator.get_page(number),
        is_writer=False,is_approver=False,original_route='market-source-original',source_search_local_only=True))
