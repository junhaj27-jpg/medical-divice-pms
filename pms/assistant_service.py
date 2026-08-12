import re
from django.db.models import Q
from django.utils import timezone
from .models import CAPA, CustomerComplaint, Profile, Recall
from .services import role, visible_complaints

DISCLAIMER="이 안내는 포트폴리오 데모용 업무 보조 정보이며 실제 규제·의료 판단을 대신하지 않습니다."
FLOW="불만 접수 → RA/QA 검토 → 이상사례 판단 → 위험평가 → CAPA 판단 → 규제보고 검토 → 리콜 검토 → 관리자 승인 → 조치 완료 → 사건 종료"
PII_PATTERNS=[re.compile(r"\b\d{6}-?[1-4]\d{6}\b"),re.compile(r"\b01[016789][ -]?\d{3,4}[ -]?\d{4}\b")]

def validate_question(text):
    text=" ".join((text or "").strip().split())
    if not text: raise ValueError("질문을 입력해 주세요.")
    if len(text)>1000: raise ValueError("질문은 1,000자 이내로 입력해 주세요.")
    if any(p.search(text) for p in PII_PATTERNS): raise ValueError("주민등록번호나 전화번호 같은 직접 식별정보는 입력할 수 없습니다.")
    return text

def _case_lines(qs):
    return "\n".join(f"- CMP-{x.pk:05d} · {x.title} · {x.get_status_display()}" for x in qs[:5]) or "- 해당 사건이 없습니다."

def answer_question(user,text):
    q=text.lower(); complaints=visible_complaints(user); privileged=role(user) in (Profile.Role.RA_QA,Profile.Role.ADMIN)
    if any(k in q for k in ("도움","뭘 물어","질문 예시","사용법")):
        intent="HELP"; body="다음 내용을 물어볼 수 있습니다.\n- 고위험 사건 현황\n- 기한 초과 사건\n- 진행 중 CAPA 또는 리콜\n- CMP-번호 사건 상태\n- PMS 업무 흐름\n- 위험등급 계산 기준"
    elif "업무 흐름" in q or "프로세스" in q or "상태 전이" in q:
        intent="WORKFLOW"; body=f"표준 데모 업무 흐름은 다음과 같습니다.\n{FLOW}\n각 단계의 필수 자료가 없으면 서버에서 다음 단계 진행을 차단합니다."
    elif "위험" in q and any(k in q for k in ("기준","계산","등급")):
        intent="RISK_RULE"; body="위험점수는 심각도(1~5) × 발생 가능성(1~5)입니다. 1~4 LOW, 5~9 MEDIUM, 10~16 HIGH, 17~25 CRITICAL이며 HIGH 이상은 CAPA 검토 대상입니다."
    elif any(k in q for k in ("critical","고위험","high")):
        intent="HIGH_RISK"; items=complaints.filter(risk_assessment__level__in=["HIGH","CRITICAL"]); body=f"접근 가능한 HIGH·CRITICAL 사건은 {items.count()}건입니다.\n{_case_lines(items)}"
    elif any(k in q for k in ("기한","초과","마감")):
        intent="OVERDUE"; items=complaints.filter(due_date__lt=timezone.localdate()).exclude(status=CustomerComplaint.Status.CLOSED); body=f"현재 기한 초과 사건은 {items.count()}건입니다.\n{_case_lines(items)}"
    elif "capa" in q or "시정" in q or "예방조치" in q:
        intent="CAPA"; items=CAPA.objects.filter(complaint__in=complaints).exclude(status=CAPA.Status.CLOSED); body=f"접근 가능한 진행 중 CAPA는 {items.count()}건입니다.\n"+("\n".join(f"- CAPA-{x.pk} · {x.title} · {x.get_status_display()} · 기한 {x.due_date}" for x in items[:5]) or "- 해당 CAPA가 없습니다.")
    elif "리콜" in q or "회수" in q:
        intent="RECALL"; items=Recall.objects.all() if privileged else Recall.objects.filter(complaint__in=complaints); items=items.exclude(progress_status=Recall.Progress.CLOSED); body=f"접근 가능한 진행 중 리콜은 {items.count()}건입니다.\n"+("\n".join(f"- RC-{x.pk} · {x.title} · {x.get_progress_status_display()} · 회수율 {x.recovery_rate}%" for x in items[:5]) or "- 해당 리콜이 없습니다.")
    else:
        match=re.search(r"(?:cmp[- ]?|사건\s*#?)(\d+)",q)
        if match:
            intent="CASE_STATUS"; item=complaints.filter(pk=int(match.group(1))).first()
            body=(f"CMP-{item.pk:05d} 사건은 현재 ‘{item.get_status_display()}’ 단계입니다. 제품은 {item.device.name}, 담당자는 {item.assignee or '미배정'}입니다." if item else "해당 사건이 없거나 현재 계정으로 접근할 수 없습니다.")
        else:
            intent="FALLBACK"; body="질문을 업무 현황 또는 절차 중심으로 다시 입력해 주세요. 예: ‘고위험 사건 보여줘’, ‘기한 초과 현황’, ‘CMP-1 상태’, ‘리콜 회수율’, ‘업무 흐름 알려줘’."
    return intent,f"{body}\n\n{DISCLAIMER}"
