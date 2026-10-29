"""Read-only revision impact: never rewrites applied deadlines or approvals."""
from django.core.exceptions import ValidationError
from .models import RuleApplication
from .regulation_documents import require_author
from .regulatory import rules_for, calculate_deadline, rule_payload
from .services import visible_complaints


def revision_impact(user, rule_id):
    require_author(user)
    rule=rules_for(user).get(pk=rule_id)
    apps=RuleApplication.objects.filter(complaint__in=visible_complaints(user),rule__family_key=rule.family_key).select_related("complaint","rule").order_by("complaint_id","-pk")
    seen=set();rows=[]
    target=rule_payload(rule)
    for app in apps:
        if app.complaint_id in seen: continue
        seen.add(app.complaint_id)
        if app.rule_id==rule.pk: continue
        previous=app.snapshot.get("rule",{})
        changed=[key for key,value in target.items() if previous.get(key)!=value]
        row=dict(complaint=app.complaint,previous_version=app.rule.version,previous_due=app.due_at,changed=changed,proposed_due=None,notice="조건·적용 범위는 담당자 확인 필요")
        basis=app.snapshot.get("inputs",{}).get("basis_at")
        if basis:
            try: row["proposed_due"]=calculate_deadline(rule,basis)["due_at"]
            except ValidationError: row["notice"]="기준 시점·시행일·휴일 범위 등으로 계산 불가 · 수동 확인 필요"
        rows.append(row)
    return dict(rule=rule,rows=rows)
