from datetime import timedelta
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from .safety import SafetyFilter, analyze_safety, detect, signals_for, review_signal, cohort
from .services import role
from .models import CAPA, Recall
from .ra_assistant import retrieve, generate_answer, summarize_case


@login_required
def dashboard(request):
    today=timezone.localdate()
    defaults=dict(start=(today-timedelta(days=29)).isoformat(),end=today.isoformat(),interval="week",example="real")
    form=SafetyFilter(request.user,request.GET or defaults)
    result=None
    if form.is_valid():
        result=analyze_safety(request.user,form.cleaned_data)
        if request.method=="POST":
            try: detect(request.user,form.cleaned_data)
            except ValidationError as exc: form.add_error(None,exc)
            else: return redirect(request.get_full_path())
        # Chart series grouped per product/LOT, with exact underlying case links.
        rows=result["timeline"]
        labels=sorted({r["bucket"].isoformat() for r in rows})
        groups={(r["device_id"],r["lot_id"]):(r["device__name"],r["lot__lot_number"]) for r in result["groups"]}
        result["chart"]=dict(labels=labels,datasets=[
            dict(label=f"{name} / {lot or 'LOT 없음'}",data=[sum(r["count"] for r in rows if r["bucket"].isoformat()==label and (r["device_id"],r["lot_id"])==key) for label in labels],device=key[0],lot=key[1])
            for key,(name,lot) in groups.items()])
    return render(request,"pms/safety.html",dict(form=form,result=result,signals=signals_for(request.user).order_by("-pk")[:100],privileged=role(request.user)!="STAFF"))


@login_required
def signal_detail(request, pk):
    signal=get_object_or_404(signals_for(request.user),pk=pk)
    ids=[c["pk"] for c in signal.snapshot["evidence"]]
    if request.method=="POST":
        try: review_signal(request.user,pk,request.POST.get("status"),request.POST.get("assignee"),request.POST.get("note",""),request.POST.get("capa") or None,request.POST.get("recall") or None)
        except ValidationError as exc: return render(request,"pms/safety_signal.html",dict(signal=signal,error=exc.messages),status=400)
        return redirect("safety-signal",pk=pk)
    return render(request,"pms/safety_signal.html",dict(signal=signal,capas=CAPA.objects.filter(complaint_id__in=ids),recalls=Recall.objects.filter(complaint_id__in=ids),history=signal.history.select_related("actor","assignee").order_by("pk")))


class EvidenceForm(forms.Form):
    question=forms.CharField(label="규정 질문",max_length=1000)
    jurisdiction=forms.CharField(label="관할 (정확히 일치)",required=False,max_length=100)
    device_id=forms.IntegerField(label="제품 ID",required=False,min_value=1)
    as_of=forms.DateField(label="기준일",widget=forms.DateInput(attrs={"type":"date"}))


@login_required
def evidence(request):
    form=EvidenceForm(request.POST if request.method=="POST" else request.GET or None)
    result=None;answer=None
    if form.is_valid():
        try:
            result=retrieve(request.user,**form.cleaned_data)
            if request.method=="POST" and request.POST.get("mode")=="ai":
                ids=request.POST.getlist("chunks")
                if any(not x.isdecimal() for x in ids): raise ValidationError("잘못된 근거 선택입니다.")
                answer=generate_answer(request.user,**form.cleaned_data,selected_ids=[int(x) for x in ids],consent=request.POST.get("consent")=="yes")
        except ValidationError as exc: form.add_error(None,exc)
    from .rule_ai import ai_available
    return render(request,"pms/ra_evidence.html",dict(form=form,result=result,answer=answer,ai_available=ai_available()))


@login_required
def case_summary(request,pk):
    from .models import CustomerComplaint
    try: summary=summarize_case(request.user,pk)
    except CustomerComplaint.DoesNotExist: raise Http404
    return render(request,"pms/ra_summary.html",summary)


@login_required
def rule_impact(request,pk):
    from .rule_impact import revision_impact
    from .models import ReportingRule
    try: context=revision_impact(request.user,pk)
    except ReportingRule.DoesNotExist: raise Http404
    return render(request,"pms/rule_impact.html",context)
