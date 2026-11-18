import difflib,hashlib
from pathlib import Path
from uuid import uuid4
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404,FileResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods,require_GET
from .market_views import market_view
from .market_service import eu_access
from .eu_legal_models import EULegalDocument
from .eu_acquisition import acquire,AcquisitionError
from .search_models import (EULegalTextVersion,EUSourceAttempt,EUSearchHead,SourceSearchExecution,SearchEvidenceAdoption)
from .search_history import (drafts_for,reviews_for,execution_access,adoption_access,adopt,draft_access,review_access)
from .source_search import candidates,digest

class AcquisitionForm(forms.Form):
    celex=forms.CharField(label='확인한 CELEX',max_length=60)
    language=forms.CharField(label='원문 언어',max_length=10)
    version=forms.CharField(label='법령 판본 식별자 (원문/통합본 CELEX)',max_length=60)
    articles=forms.CharField(label='가져올 조항 번호 (예: 87,88,89)',initial='87,88,89')
    file=forms.FileField(label='공식 PDF 또는 HTML 파일',required=False)
    source_url=forms.URLField(label='다운로드한 공식 URL (선택)',max_length=1500,required=False)
    op_page=forms.URLField(label='동일 CELEX의 Publications Office 상세 URL (선택)',max_length=1500,required=False)
    confirm=forms.BooleanField(label='공식 사이트에서 확인한 동일 문서·언어·판본이며, 근거 채택은 별도 RA 검토함')
    def __init__(self,*args,document,**kwargs):
        self.document=document;super().__init__(*args,**kwargs)
    def clean(self):
        data=super().clean();expected=self.document.celex or self.document.identifier
        if data.get('celex')!=expected or data.get('version')!=expected or data.get('language')!=self.document.language:
            raise ValidationError('선택한 문서의 CELEX·언어·판본과 일치해야 합니다. 다른 판본은 EU 원문 문서로 따로 등록하세요.')
        try:data['article_numbers']=[int(n.strip()) for n in data.get('articles','').split(',')]
        except ValueError:raise ValidationError('조항 번호를 확인하세요.')
        return data

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def manage_eu(request,pk):
    if not eu_access(request.user):raise Http404
    doc=get_object_or_404(EULegalDocument,pk=pk);status=200;message=''
    initial={'celex':doc.celex or doc.identifier,'version':doc.celex or doc.identifier,'language':doc.language}
    form=AcquisitionForm(request.POST if request.method=='POST' else None,request.FILES or None,document=doc,initial=initial)
    if request.method=='POST' and form.is_valid():
        temporary=None
        try:
            values=form.cleaned_data;file=values.get('file')
            if request.POST.get('action')=='import':
                if not file:raise ValidationError('공식 PDF/HTML 파일을 선택하세요.')
                suffix=Path(file.name).suffix.lower()
                if suffix not in ('.pdf','.html','.htm') or file.size>20*1024*1024:raise ValidationError('20MB 이하 공식 PDF/HTML만 지원합니다.')
                folder=Path(settings.MEDIA_ROOT)/'eu_import_inbox';folder.mkdir(parents=True,exist_ok=True)
                temporary=folder/(uuid4().hex+suffix)
                with temporary.open('wb') as stream:
                    for block in file.chunks():stream.write(block)
            elif request.POST.get('action')!='fetch':raise ValidationError('가져오기 방식을 확인하세요.')
            row,created=acquire(doc,request.user,values['article_numbers'],input_file=temporary,source_url=values.get('source_url'),op_page=values.get('op_page'))
            message=f'본문 text-v{row.version} '+('검증·추출 완료. 색인 완료 후 게시됩니다.' if created else '동일 본문을 재사용했습니다.')
        except (AcquisitionError,ValidationError,OSError) as exc:form.add_error(None,str(exc));status=400
        finally:
            if temporary:temporary.unlink(missing_ok=True)
    elif request.method=='POST':status=400
    head=EUSearchHead.objects.filter(document=doc).select_related('active_text').first()
    success=doc.source_attempts.filter(status='SUCCESS').order_by('-pk').first()
    latest=doc.search_text_versions.order_by('-version').first()
    return render(request,'pms/markets/search_eu_manage.html',dict(doc=doc,form=form,head=head,latest=latest,success=success,
        attempts=doc.source_attempts.order_by('-pk')[:30],message=message,source_search_local_only=True),status=status)

@market_view
@never_cache
@require_GET
def eu_text(request,pk,download=False):
    if not eu_access(request.user):raise Http404
    text=get_object_or_404(EULegalTextVersion.objects.select_related('document'),pk=pk)
    if digest(text.text)!=text.content_hash:raise Http404
    if download:
        if not text.original_file:raise Http404
        root=Path(settings.MEDIA_ROOT).resolve();path=Path(text.original_file.path).resolve()
        if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=text.original_hash:raise Http404
        response=FileResponse(path.open('rb'),as_attachment=True,filename=f'{text.document.celex}-text-v{text.version}{path.suffix}')
        response['Content-Security-Policy']="sandbox; default-src 'none'";return response
    return render(request,'pms/markets/search_eu_text.html',dict(text=text,source_search_local_only=True))

class AdoptionForm(forms.Form):
    key=forms.CharField(max_length=180,widget=forms.HiddenInput)
    draft=forms.ModelChoiceField(label='연결할 기존 문서 초안',queryset=None,required=False)
    review=forms.ModelChoiceField(label='연결할 기존 RA 비교 검토 기록',queryset=None,required=False)
    rationale=forms.CharField(label='근거 채택 사유',max_length=2000,widget=forms.Textarea)
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs);self.fields['draft'].queryset=drafts_for(user);self.fields['review'].queryset=reviews_for(user)

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def execution_detail(request,pk):
    event=get_object_or_404(SourceSearchExecution,pk=pk)
    if not execution_access(request.user,event):raise Http404
    form=AdoptionForm(request.POST if request.method=='POST' else None,user=request.user,initial={'key':request.GET.get('key','')})
    if request.method=='POST' and form.is_valid():
        try:
            row,_=adopt(request.user,event,**form.cleaned_data)
            return redirect('market-search-adoption',row.pk)
        except ValidationError as exc:form.add_error(None,exc)
    return render(request,'pms/markets/search_execution.html',dict(event=event,form=form,source_search_local_only=True),status=400 if request.method=='POST' else 200)

@market_view
@never_cache
@require_GET
def history(request):
    events=SourceSearchExecution.objects.filter(actor=request.user).order_by('-pk')[:100]
    events=[event for event in events if execution_access(request.user,event)]
    rows=SearchEvidenceAdoption.objects.select_related('draft__project__device','review__result__run').order_by('-pk')
    for field in ('draft','review'):
        value=request.GET.get(field)
        if value:
            if not value.isdecimal() or len(value)>18:raise Http404
            rows=rows.filter(**{field+'_id':int(value)})
    rows=[row for row in rows[:100] if adoption_access(request.user,row)]
    return render(request,'pms/markets/search_history.html',dict(events=events,adoptions=rows,source_search_local_only=True))

@market_view
@never_cache
@require_GET
def adoption_detail(request,pk):
    row=get_object_or_404(SearchEvidenceAdoption.objects.select_related('draft__project__device','review__result__run'),pk=pk)
    if not adoption_access(request.user,row):raise Http404
    original=row.snapshot
    available=candidates(request.user,include_history=True)
    matches=[r for r in available if r['kind']==original['kind'] and r['document_id']==original['document_id'] and r['section']==original['section']]
    if original['kind']=='fda':
        from .fda_library_models import FDAReferenceVersion
        old=FDAReferenceVersion.objects.get(pk=original['source_id'])
        versions=set(FDAReferenceVersion.objects.filter(key=old.key).values_list('pk',flat=True))
        matches=[r for r in available if r['kind']=='fda' and r['source_id'] in versions and r['section']==original['section']]
    current=max(matches,key=lambda r:(r['source_id'],r['ordinal']==original['ordinal']),default=None)
    diff='\n'.join(difflib.unified_diff(original['text'].splitlines(),current['text'].splitlines(),fromfile=original['version'],tofile=current['version'],lineterm='')) if current else '현재 접근 가능한 동일 조항 본문이 없습니다. 채택 당시 스냅샷은 보존됩니다.'
    return render(request,'pms/markets/search_adoption.html',dict(item=row,current=current,diff=diff or '본문 변경 없음',source_search_local_only=True))
