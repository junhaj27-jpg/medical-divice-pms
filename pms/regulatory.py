"""Evidence-backed rules: explicit human approval, deterministic deadlines, immutable snapshots."""
import csv
import hashlib
import io
import json
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Max
from django.utils import timezone
from .models import (ReportingRule, RuleApplication, RuleCitation, RulePreview, RuleChange,
                     RuleFamilyLock, RegulationChunk, CustomerComplaint)
from .services import role, audit, visible_complaints
from .regulation_documents import require_author, require_approver, can_write, documents_for
from .file_security import safe_attachment_bytes

CONTENT_FIELDS=("name","conditions","basis","days","day_type","holidays","effective_on","change_reason","is_example","jurisdiction","device_id","scope_description","reporting_authority","obligation_trigger","deadline_expression","deadline_unit","include_start","deadline_time","timezone_name","exceptions","effective_until","holiday_verified_from","holiday_verified_until","holiday_checked_on","unresolved_items","source_expressions","origin")
FIELD_LABELS={"jurisdiction":"관할","scope_description":"적용 대상·범위","conditions":"적용 조건","reporting_authority":"보고 대상 기관","obligation_trigger":"의무 발생 사건","basis":"기한 기준 시점","days":"기한 값","deadline_unit":"기한 단위","day_type":"달력일·영업일","include_start":"시작일 포함 여부","deadline_time":"마감 시각","timezone_name":"시간대","exceptions":"예외 조건","effective_on":"시행일","deadline_expression":"기한 원문 표현"}
DISPLAY_LABELS={**FIELD_LABELS,"name":"규칙명","device_id":"대상 제품 번호","holidays":"휴일 날짜·명칭","change_reason":"변경 사유","is_example":"테스트·예시 여부","effective_until":"시행 종료일","holiday_verified_from":"휴일 확인 시작일","holiday_verified_until":"휴일 확인 종료일","holiday_checked_on":"휴일 마지막 확인일","unresolved_items":"확인 필요·문서 충돌","source_expressions":"항목별 원문 표현","origin":"작성 방식","family_key":"규칙 계열 식별자","version":"버전","citations":"항목별 근거 인용"}
PUBLISHED=("APPROVED","EFFECTIVE","RETIRED")


def rules_for(user):
    qs=ReportingRule.objects.select_related("created_by","approved_by","supersedes","device")
    if not user.is_authenticated: return qs.none()
    if role(user)=="ADMIN": return qs
    if can_write(user) or role(user) in settings.RULE_APPROVER_ROLES:
        states=list(PUBLISHED)+["LEGACY"]
        if role(user) in settings.RULE_APPROVER_ROLES: states.append("REVIEW")
        return qs.filter(Q(state__in=states)|Q(created_by=user))
    return qs.filter(state__in=PUBLISHED)


def editable(rule,user):
    require_author(user)
    if rule.state!="DRAFT" or (rule.created_by_id!=user.pk and role(user)!="ADMIN"): raise PermissionDenied("본인 초안만 수정할 수 있습니다. 승인된 규칙은 개정하세요.")


def json_value(value): return json.loads(json.dumps(value,default=str,ensure_ascii=False))


def citation_data(rule):
    return [{"id":c.pk,"field":c.field_name,"quote":c.quote,"interpretation":c.interpretation,"chunk_id":c.chunk_id,"chunk_hash":c.chunk.content_hash,"document_id":c.chunk.document_id,"document":c.chunk.document.title,"edition":c.chunk.document.edition,"sha256":c.chunk.document.sha256,"page":c.chunk.page,"section":c.chunk.section,"paragraph":c.chunk.paragraph,"sequence":c.chunk.sequence,"effective_on":str(c.chunk.document.effective_on or ""),"official_url":c.chunk.document.official_url} for c in rule.citations.select_related("chunk__document").order_by("pk")]


def rule_payload(rule):
    return json_value({**{key:getattr(rule,key) for key in CONTENT_FIELDS},"family_key":str(rule.family_key),"version":rule.version,"citations":citation_data(rule) if rule.pk else []})


def fingerprint(rule): return hashlib.sha256(json.dumps(rule_payload(rule),sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def record_change(rule,user,action,reason,before):
    after={**rule_payload(rule),"state":rule.state,"revision":rule.revision}
    RuleChange.objects.create(rule=rule,actor=user,action=action,reason=reason,before=before,after=after)
    audit(user,action,rule,after={"state":rule.state,"version":rule.version,"revision":rule.revision,"changed_fields":[k for k in after if after[k]!=before.get(k)],"reason":reason})


def snapshot_before(rule): return {**rule_payload(rule),"state":rule.state,"revision":rule.revision}


def normalize_holidays(values):
    if not isinstance(values,list): raise ValidationError("휴일은 날짜·명칭 목록이어야 합니다.")
    result=[];seen=set()
    for value in values:
        if isinstance(value,str): day=value;name=""  # Retain legacy dates; approval requires a reviewed name.
        elif isinstance(value,dict) and set(value)<= {"date","name"}: day=value.get("date");name=value.get("name","")
        else: raise ValidationError("휴일 항목은 date/name 구조여야 합니다.")
        try: parsed=date.fromisoformat(day)
        except (ValueError,TypeError): raise ValidationError("휴일 날짜는 YYYY-MM-DD 형식이어야 합니다.")
        if not isinstance(name,str) or len(name)>160: raise ValidationError("휴일 명칭은 160자 이내 문자열입니다.")
        if parsed in seen: raise ValidationError(f"중복 휴일 날짜: {day}")
        seen.add(parsed);result.append({"date":parsed.isoformat(),"name":name.strip()})
    return sorted(result,key=lambda x:x["date"])


def validate_rule_content(rule):
    if not isinstance(rule.conditions,dict) or set(rule.conditions)-{"complaint_type","risk_level","serious"}: raise ValidationError("조건은 complaint_type/risk_level/serious 동등 비교만 허용합니다.")
    for key,value in rule.conditions.items():
        if key=="serious" and type(value) is not bool: raise ValidationError("serious는 true/false여야 합니다.")
        if key=="risk_level" and value not in ("LOW","MEDIUM","HIGH","CRITICAL"): raise ValidationError("위험등급을 확인하세요.")
        if key=="complaint_type" and (not isinstance(value,str) or not value.strip() or len(value)>50): raise ValidationError("사건 유형을 확인하세요.")
    normalize_holidays(rule.holidays)
    if rule.timezone_name:
        try: ZoneInfo(rule.timezone_name)
        except (ZoneInfoNotFoundError,ValueError): raise ValidationError("유효한 IANA 시간대가 필요합니다.")
    if not isinstance(rule.unresolved_items,list) or any(not isinstance(x,str) for x in rule.unresolved_items): raise ValidationError("확인 필요 사항은 문자열 배열이어야 합니다.")
    if not isinstance(rule.source_expressions,dict) or any(k not in FIELD_LABELS or not isinstance(v,str) for k,v in rule.source_expressions.items()): raise ValidationError("항목별 원문 표현 구조를 확인하세요.")
    if rule.effective_on and rule.effective_until and rule.effective_until<rule.effective_on: raise ValidationError("시행 종료일이 시행일보다 빠릅니다.")
    if rule.holiday_verified_from and rule.holiday_verified_until and rule.holiday_verified_until<rule.holiday_verified_from: raise ValidationError("휴일 확인 기간을 확인하세요.")
    if rule.holiday_checked_on and rule.holiday_checked_on>timezone.localdate(): raise ValidationError("마지막 확인일은 미래일 수 없습니다.")
    if not rule.change_reason.strip(): raise ValidationError("변경 사유는 필수입니다.")


@transaction.atomic
def save_draft(rule,user,reason,expected_revision=None):
    require_author(user)
    if not reason.strip(): raise ValidationError("변경 사유를 입력하세요.")
    before={}
    if rule.pk:
        old=ReportingRule.objects.select_for_update(of=("self",)).get(pk=rule.pk);editable(old,user)
        if expected_revision is None or old.revision!=expected_revision: raise ValidationError("다른 사용자가 수정했습니다. 새로고침 후 다시 저장하세요.")
        before=snapshot_before(old);rule.created_by=old.created_by;rule.family_key=old.family_key;rule.version=old.version;rule.state=old.state;rule.revision=old.revision+1
    else:
        rule.created_by=user;rule.state="DRAFT"
        if ReportingRule.objects.filter(name=rule.name).exists(): raise ValidationError("동일 이름 규칙이 있습니다. 해당 규칙에서 개정 초안을 만드세요.")
        RuleFamilyLock.objects.get_or_create(key=rule.family_key)
    rule.change_reason=reason;rule._workflow_write=True;rule.save()
    record_change(rule,user,"RULE_DRAFT_SAVE",reason,before);return rule


@transaction.atomic
def revise_rule(source,user,reason):
    require_author(user);source=rules_for(user).select_for_update(of=("self",)).get(pk=source.pk)
    if not reason.strip(): raise ValidationError("개정 사유를 입력하세요.")
    lock,_=RuleFamilyLock.objects.get_or_create(key=source.family_key)
    RuleFamilyLock.objects.select_for_update(of=("self",)).get(pk=lock.pk)
    version=(ReportingRule.objects.filter(family_key=source.family_key).aggregate(n=Max("version"))["n"] or 0)+1
    values={key:getattr(source,key) for key in CONTENT_FIELDS}
    values.update(change_reason=reason,origin="MANUAL")
    new=ReportingRule(**values,family_key=source.family_key,version=version,supersedes=source,created_by=user,state="DRAFT")
    new._workflow_write=True;new.save()
    for citation in source.citations.all():
        RuleCitation.objects.create(rule=new,field_name=citation.field_name,chunk=citation.chunk,quote=citation.quote,interpretation=citation.interpretation,created_by=user)
    record_change(new,user,"RULE_REVISE",reason,{"source_id":source.pk,"source_version":source.version});return new


@transaction.atomic
def add_citation(rule,user,field_name,chunk,quote,interpretation,reason):
    rule=ReportingRule.objects.select_for_update(of=("self",)).get(pk=rule.pk);editable(rule,user)
    if not reason.strip(): raise ValidationError("근거 변경 사유가 필요합니다.")
    if field_name not in FIELD_LABELS: raise ValidationError("지원하지 않는 근거 항목입니다.")
    if not documents_for(user).filter(pk=chunk.document_id).exists(): raise PermissionDenied
    safe_attachment_bytes(chunk.document)
    if chunk.document.extraction_status!="READY" or not quote.strip() or quote.strip() not in chunk.text: raise ValidationError("인용은 추출된 해당 청크의 실제 문장이어야 합니다.")
    before=snapshot_before(rule)
    citation=RuleCitation.objects.create(rule=rule,field_name=field_name,chunk=chunk,quote=quote.strip(),interpretation=interpretation.strip(),created_by=user)
    previous=rule.citations.filter(field_name=field_name).exclude(chunk__document_id=chunk.document_id).select_related("chunk__document")
    if previous.exists():
        note=f"복수 문서 근거 검토 필요: {FIELD_LABELS[field_name]} / {chunk.document.title} {chunk.document.edition} ↔ "+" / ".join(f"{c.chunk.document.title} {c.chunk.document.edition}" for c in previous)
        rule.unresolved_items=list(dict.fromkeys([*rule.unresolved_items,note]))
    rule.revision+=1;rule._workflow_write=True;rule.save();record_change(rule,user,"RULE_CITATION_ADD",reason,before);return citation


@transaction.atomic
def remove_citation(citation,user,reason):
    rule=ReportingRule.objects.select_for_update(of=("self",)).get(pk=citation.rule_id);editable(rule,user)
    if not reason.strip(): raise ValidationError("근거 제거 사유를 입력하세요.")
    before=snapshot_before(rule);citation.delete();rule.revision+=1;rule._workflow_write=True;rule.save();record_change(rule,user,"RULE_CITATION_REMOVE",reason,before)


@transaction.atomic
def import_holidays(rule,user,file,reason):
    rule=ReportingRule.objects.select_for_update(of=("self",)).get(pk=rule.pk);editable(rule,user)
    if not reason.strip(): raise ValidationError("휴일 변경 사유를 입력하세요.")
    if file.size>262144: raise ValidationError("휴일 CSV는 256KB 이하입니다.")
    try:
        reader=csv.DictReader(io.StringIO(file.read().decode("utf-8-sig")))
        if reader.fieldnames not in (["date","name"],["날짜","명칭"]): raise ValidationError("CSV 헤더는 date,name 또는 날짜,명칭이어야 합니다.")
        values=[{"date":row.get("date",row.get("날짜")),"name":row.get("name",row.get("명칭"))} for row in reader]
    except UnicodeError: raise ValidationError("CSV는 UTF-8이어야 합니다.")
    normalized=normalize_holidays(values)
    if any(not x["name"] for x in normalized): raise ValidationError("CSV 휴일 명칭은 필수입니다.")
    before=snapshot_before(rule);rule.holidays=normalized;rule.revision+=1;rule.change_reason=reason;rule._workflow_write=True;rule.save()
    record_change(rule,user,"RULE_HOLIDAY_IMPORT",reason,before);return rule


def overlaps(a,b):
    if a.jurisdiction!=b.jurisdiction: return False
    if a.device_id and b.device_id and a.device_id!=b.device_id: return False
    if any(key in b.conditions and b.conditions[key]!=value for key,value in a.conditions.items()): return False
    start=max(a.effective_on or date.min,b.effective_on or date.min)
    end=min(a.effective_until or date.max,b.effective_until or date.max)
    return start<=end


def conflicts(rule,states=("APPROVED","EFFECTIVE")):
    return [other for other in ReportingRule.objects.filter(state__in=states,jurisdiction=rule.jurisdiction).exclude(pk=rule.pk) if overlaps(rule,other)]


def readiness(rule,user):
    errors=[]
    needed=list(FIELD_LABELS)
    if rule.deadline_unit=="HOURS": needed.remove("deadline_time")
    for key in needed:
        value=getattr(rule,key)
        if value is None or (isinstance(value,str) and not value.strip()): errors.append(f"{FIELD_LABELS[key]}: 확인 필요")
    if rule.unresolved_items: errors.append("확인 필요·문서 간 충돌 사항을 먼저 해소하세요: "+" / ".join(rule.unresolved_items))
    citations=list(rule.citations.select_related("chunk__document"));by_field={}
    checked={}
    for c in citations:
        by_field.setdefault(c.field_name,[]).append(c)
        doc=c.chunk.document
        if c.quote not in c.chunk.text or hashlib.sha256(c.chunk.text.encode()).hexdigest()!=c.chunk.content_hash: errors.append("원문 인용 무결성을 확인하세요.")
        if doc.pk not in checked:
            try: safe_attachment_bytes(doc);checked[doc.pk]=True
            except (PermissionDenied,OSError): errors.append(f"문서 검사·무결성 미통과: {doc.title}");checked[doc.pk]=False
        if not documents_for(user).filter(pk=doc.pk).exists() or doc.visibility!="TEAM": errors.append("공동 검토 가능한 근거 문서가 필요합니다.")
        if doc.review_status!="REVIEWED" or doc.extraction_status!="READY": errors.append(f"문서 검토·추출 미완료: {doc.title}")
        if doc.jurisdiction!=rule.jurisdiction or (doc.device_id and doc.device_id!=rule.device_id): errors.append(f"문서 적용 범위 불일치: {doc.title}")
        if doc.effective_on and rule.effective_on and doc.effective_on>rule.effective_on: errors.append("근거 문서 시행일보다 빠른 규칙 시행일입니다.")
        if doc.is_example and not rule.is_example: errors.append("테스트 문서를 실제 운영 규칙의 근거로 사용할 수 없습니다.")
    for key in needed:
        if key not in by_field: errors.append(f"{FIELD_LABELS[key]}: 항목별 근거 인용이 필요합니다.")
    if not citations: errors.append("근거 문서와 인용 위치가 필요합니다.")
    if any(term in rule.deadline_expression for term in ("즉시","인지한 날","지체 없이")):
        for key in ("basis","days"):
            if not any(c.interpretation.strip() for c in by_field.get(key,[])): errors.append("해석이 필요한 원문은 RA 해석 근거를 명시해야 합니다. 자동 숫자·기준 변환은 하지 않습니다.")
    if rule.origin=="AI":
        if not any(str(rule.days) in c.quote for c in by_field.get("days",[])): errors.append("AI 제안 숫자에 대응하는 실제 인용이 없습니다.")
    if rule.day_type=="BUSINESS":
        if not all((rule.holiday_verified_from,rule.holiday_verified_until,rule.holiday_checked_on)): errors.append("휴일 확인 범위와 마지막 확인일이 필요합니다.")
        if any(not h["name"] for h in normalize_holidays(rule.holidays)): errors.append("휴일 명칭을 확인하세요.")
    return list(dict.fromkeys(errors))


def parse_basis(value,zone):
    if isinstance(value,str):
        try: value=datetime.fromisoformat(value.strip().replace("Z","+00:00"))
        except ValueError: raise ValidationError("기준 일시는 ISO 형식으로 입력하세요.")
    if not isinstance(value,datetime): raise ValidationError("기준 일시가 필요합니다.")
    if timezone.is_naive(value):
        first=value.replace(tzinfo=zone,fold=0);second=value.replace(tzinfo=zone,fold=1)
        if first.utcoffset()!=second.utcoffset() or first.astimezone(dt_timezone.utc).astimezone(zone).replace(tzinfo=None)!=value:
            raise ValidationError("DST 중복·존재하지 않는 시각입니다. UTC 오프셋을 명시하세요.")
        value=first
    return value.astimezone(zone)


def calculate_deadline(rule,basis_at):
    validate_rule_content(rule)
    if rule.days is None or not rule.deadline_unit or not rule.day_type or rule.include_start is None or not rule.timezone_name or not rule.basis:
        raise ValidationError("기한 값·단위·달력 기준·시작일 포함·시간대·기준 시점을 확인하세요.")
    zone=ZoneInfo(rule.timezone_name);base=parse_basis(basis_at,zone)
    if rule.effective_on and base.date()<rule.effective_on: raise ValidationError("기준 일시가 규칙 시행일보다 빠릅니다.")
    if rule.effective_until and base.date()>rule.effective_until: raise ValidationError("기준 일시가 규칙 시행 기간을 벗어납니다.")
    excluded=[];holidays={h['date']:h['name'] for h in normalize_holidays(rule.holidays)}
    def verified(day):
        if not rule.holiday_verified_from or not rule.holiday_verified_until or not rule.holiday_checked_on or not rule.holiday_verified_from<=day<=rule.holiday_verified_until:
            raise ValidationError("휴일 확인 범위를 벗어납니다. 확인 범위를 등록하기 전 자동 확정할 수 없습니다.")
    if rule.deadline_unit=="HOURS":
        if rule.day_type!="CALENDAR" or rule.include_start: raise ValidationError("시간 단위는 달력 경과시간·시작일 포함 안 함만 지원합니다.")
        due=(base.astimezone(dt_timezone.utc)+timedelta(hours=rule.days)).astimezone(zone)
    else:
        if rule.deadline_time is None: raise ValidationError("마감 시각을 입력하세요.")
        day=base.date();remaining=rule.days
        if rule.day_type=="BUSINESS": verified(day)
        if remaining:
            if not rule.include_start: day+=timedelta(days=1)
            while True:
                if rule.day_type=="BUSINESS": verified(day)
                if rule.day_type=="BUSINESS" and (day.weekday()>=5 or day.isoformat() in holidays):
                    excluded.append({"date":day.isoformat(),"reason":holidays.get(day.isoformat(),"주말")})
                else: remaining-=1
                if not remaining: break
                day+=timedelta(days=1)
        due=parse_basis(datetime.combine(day,rule.deadline_time),zone)
    if due<base: raise ValidationError("최종 기한이 기준 일시보다 빠릅니다. 시작일 포함과 마감 시각을 확인하세요.")
    coverage={"from":str(rule.holiday_verified_from or ""),"until":str(rule.holiday_verified_until or ""),"checked_on":str(rule.holiday_checked_on or "")}
    method="토·일 및 해당 버전 등록 휴일만 제외. 공휴일 자동 갱신 없음." if rule.day_type=="BUSINESS" else "달력 경과일·시간 기준이며 주말·휴일을 제외하지 않습니다."
    return {"rule_name":rule.name,"basis_label":rule.get_basis_display(),"holiday_coverage":coverage,"basis_at":base.isoformat(),"basis_type":rule.basis,"include_start":rule.include_start,"excluded":excluded,"due_at":due.isoformat(),"timezone":rule.timezone_name,"rule_id":rule.pk,"version":rule.version,"deadline_unit":rule.deadline_unit,"value":rule.days,"sources":citation_data(rule),"fingerprint":fingerprint(rule),"calendar_method":method}


@transaction.atomic
def preview_rule(rule,user,basis_at):
    require_author(user)
    rule=rules_for(user).get(pk=rule.pk)
    result=calculate_deadline(rule,basis_at)
    return RulePreview.objects.create(rule=rule,created_by=user,fingerprint=result["fingerprint"],inputs={"basis_at":result["basis_at"]},result=result)


@transaction.atomic
def transition_rule(rule,user,action,reason):
    if not reason.strip(): raise ValidationError("상태 변경 사유를 입력하세요.")
    if action in ("activate","retire"):
        scope_lock=uuid.UUID(int=0)
        RuleFamilyLock.objects.get_or_create(key=scope_lock)
        RuleFamilyLock.objects.filter(pk=scope_lock).update(key=scope_lock)
    rule=rules_for(user).select_for_update(of=("self",)).get(pk=rule.pk);before=snapshot_before(rule)
    if action=="submit":
        editable(rule,user);errors=readiness(rule,user)
        if errors: raise ValidationError(errors)
        if not rule.previews.filter(fingerprint=fingerprint(rule)).exists(): raise ValidationError("현재 초안의 기한 미리보기를 먼저 통과하세요.")
        rule.state="REVIEW"
    elif action=="reject":
        require_approver(user)
        if rule.state!="REVIEW": raise ValidationError("검토 요청 상태만 반려할 수 있습니다.")
        rule.state="DRAFT";rule.reviewed_by=user
    elif action=="approve":
        require_approver(user)
        if rule.state!="REVIEW": raise ValidationError("검토 요청 상태만 승인할 수 있습니다.")
        if settings.RULE_REQUIRE_SEPARATION and rule.created_by_id==user.pk: raise ValidationError("작성자와 승인자를 분리해야 합니다.")
        errors=readiness(rule,user)
        if errors: raise ValidationError(errors)
        preview=rule.previews.filter(fingerprint=fingerprint(rule)).order_by("-pk").first()
        if not preview: raise ValidationError("변경 후 기한 미리보기가 필요합니다.")
        result=calculate_deadline(rule,preview.inputs["basis_at"])
        if result!=preview.result: raise ValidationError("계산 결과가 변경되었습니다. 다시 검증하세요.")
        rule.state="APPROVED";rule.approved_by=user;rule.reviewed_by=user;rule.approved_at=timezone.now()
    elif action=="activate":
        require_approver(user)
        if settings.RULE_REQUIRE_SEPARATION and rule.created_by_id==user.pk: raise ValidationError("작성자 본인은 시행 승인할 수 없습니다.")
        if rule.state!="APPROVED": raise ValidationError("승인된 규칙만 시행할 수 있습니다.")
        today=timezone.now().astimezone(ZoneInfo(rule.timezone_name)).date()
        if not rule.effective_on or today<rule.effective_on or (rule.effective_until and today>rule.effective_until): raise ValidationError("시행 기간이 아닙니다.")
        errors=readiness(rule,user)
        if errors: raise ValidationError(errors)
        if conflicts(rule,states=("EFFECTIVE",)): raise ValidationError("적용 범위·시행 기간이 겹치는 시행 규칙이 있습니다. 충돌을 해소하세요.")
        rule.state="EFFECTIVE";rule.activated_at=timezone.now()
    elif action=="retire":
        require_approver(user)
        if rule.state not in ("APPROVED","EFFECTIVE"): raise ValidationError("승인·시행 상태만 폐기할 수 있습니다.")
        rule.state="RETIRED"
    else: raise ValidationError("지원하지 않는 상태 변경입니다.")
    rule._workflow_write=True;rule.save();record_change(rule,user,"RULE_"+action.upper(),reason,before);return rule


def matches_case(rule,complaint):
    values={"complaint_type":complaint.complaint_type,"risk_level":getattr(getattr(complaint,"risk_assessment",None),"level",None),"serious":getattr(getattr(complaint,"adverse_event",None),"serious",False)}
    return (not rule.device_id or complaint.device_id==rule.device_id) and all(values[k]==v for k,v in rule.conditions.items())


@transaction.atomic
def apply_regulated_rule(complaint,rule,user,preview,reason,confirmed_previous,confirmed_due_date=None,expected_case_token=None,expected_rule_token=None):
    require_author(user)
    if not reason.strip(): raise ValidationError("적용·재산정 사유를 입력하세요.")
    scope_lock=uuid.UUID(int=0)
    RuleFamilyLock.objects.get_or_create(key=scope_lock)
    RuleFamilyLock.objects.filter(pk=scope_lock).update(key=scope_lock)
    c=visible_complaints(user).select_for_update(of=("self",)).get(pk=complaint.pk)
<<<<<<< HEAD
    rule=rules_for(user).select_for_update().get(pk=rule.pk)
=======
    rule=rules_for(user).select_for_update(of=("self",)).get(pk=rule.pk)
    if expected_case_token or expected_rule_token:
        from .impact import case_token, rule_token
        if expected_case_token!=case_token(c) or expected_rule_token!=rule_token(rule): raise ValidationError("분석 이후 자료가 변경되었습니다. 재분석하세요.")
    if c.status=="CLOSED": raise ValidationError("종료 사건은 규칙을 재적용할 수 없습니다.")
>>>>>>> 243e562e399fc29d60693843cff3275fba58fa23
    if rule.state!="EFFECTIVE": raise ValidationError("승인 후 시행된 규칙만 사건에 적용할 수 있습니다.")
    today=timezone.now().astimezone(ZoneInfo(rule.timezone_name)).date()
    if today<rule.effective_on or (rule.effective_until and today>rule.effective_until): raise ValidationError("현재 시행 기간이 아닙니다.")
    if rule.is_example and not c.is_example: raise ValidationError("테스트용 규칙은 테스트 사건에만 적용할 수 있습니다.")
    if not matches_case(rule,c): raise ValidationError("사건이 규칙의 대상 제품·조건과 일치하지 않습니다.")
    if conflicts(rule,states=("EFFECTIVE",)): raise ValidationError("시행 규칙 충돌을 해소한 뒤 적용하세요.")
    errors=readiness(rule,user)
    if errors: raise ValidationError(errors)
    preview=RulePreview.objects.get(pk=preview.pk,rule=rule,created_by=user)
    if preview.fingerprint!=fingerprint(rule): raise ValidationError("규칙이 변경되었습니다. 다시 미리보기를 실행하세요.")
    result=calculate_deadline(rule,preview.inputs["basis_at"])
    if result!=preview.result: raise ValidationError("계산 결과가 변경되었습니다.")
    base=parse_basis(preview.inputs["basis_at"],ZoneInfo(rule.timezone_name))
    if rule.basis in ("REPORTED","OCCURRED"):
        expected=c.reported_on if rule.basis=="REPORTED" else c.occurred_on
        if base.date()!=expected: raise ValidationError("선택한 기준 일자가 사건의 접수일·발생일과 일치하지 않습니다.")
    previous=c.rule_applications.order_by("-pk").first()
    previous_id=previous.pk if previous else 0
    if confirmed_due_date!=str(c.due_date or ""): raise ValidationError("사건 기한이 변경되었습니다. 변경 전후를 다시 확인하세요.")
    if confirmed_previous!=previous_id: raise ValidationError("사건 기한이 변경되었습니다. 변경 전후를 다시 확인하세요.")
    before={"due_date":str(c.due_date or ""),"application_id":previous_id,"due_at":previous.due_at.isoformat() if previous else None}
    due=datetime.fromisoformat(result["due_at"])
    snapshot={"rule":rule_payload(rule),"inputs":preview.inputs,"calculation":result,"preview_id":preview.pk,"previous":before}
    application=RuleApplication.objects.create(complaint=c,rule=rule,snapshot=snapshot,due_at=due,actor=user,reason=reason,previous_snapshot=before)
    c.due_date=due.astimezone(ZoneInfo(rule.timezone_name)).date();c.save(update_fields=["due_date","updated_at"])
    audit(user,"RULE_CASE_APPLY",application,before,{"due_at":due.isoformat(),"rule_id":rule.pk,"version":rule.version,"reason":reason})
    return application
