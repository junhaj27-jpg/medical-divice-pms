from django import forms
from .forms import StyledForm
from .models import WorkTask, CAPAEvaluation, RecallRecipient, RecallContact, ReportingRule, BusinessPartner


class TaskForm(StyledForm):
    class Meta:
        model=WorkTask
        fields=("complaint","capa","recall","assignee","title","description","priority","due_at","status")
        widgets={"due_at":forms.DateTimeInput(format="%Y-%m-%dT%H:%M",attrs={"type":"datetime-local"})}

class EvaluationForm(StyledForm):
    class Meta:
        model=CAPAEvaluation
        fields=("action_result","criteria","scheduled_on","evaluated_on","verdict","rationale","evidence")
        widgets={k:forms.DateInput(attrs={"type":"date"}) for k in ("scheduled_on","evaluated_on")}

class RecipientForm(StyledForm):
    class Meta:
        model=RecallRecipient
        fields=("lot","partner","unit","target_quantity","notified_on","notification_method","replied_on","reply_status","unrecovered_reason")
        widgets={k:forms.DateInput(attrs={"type":"date"}) for k in ("notified_on","replied_on")}

class ContactForm(StyledForm):
    class Meta:
        model=RecallContact
        fields=("contacted_at","method","note")
        widgets={"contacted_at":forms.DateTimeInput(attrs={"type":"datetime-local"})}

class RecoveryForm(forms.Form):
    quantity=forms.IntegerField(label="회수 수량",min_value=1)
    recovered_on=forms.DateField(label="회수 일자",widget=forms.DateInput(attrs={"type":"date"}))

class RuleForm(StyledForm):
    class Meta:
        model=ReportingRule
        fields=("name","conditions","basis","days","day_type","holidays","effective_on","change_reason","is_example")
        widgets={"effective_on":forms.DateInput(attrs={"type":"date"})}

class ApplyRuleForm(forms.Form):
    name=forms.ChoiceField(label="적용 규칙")
    reason=forms.CharField(label="적용·재적용 사유",widget=forms.Textarea)

class PartnerForm(StyledForm):
    class Meta: model=BusinessPartner; fields=("name",)
