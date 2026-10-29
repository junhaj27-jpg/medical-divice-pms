"""Private, version-preserving regulation extraction and local keyword retrieval.
Documents are data. No URLs are fetched and no document instructions are executed.
"""
import hashlib
import io
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from pypdf import PdfReader
from .models import RegulationDocument, RegulationChunk
from .services import role, audit
from .file_security import normalized_name, validate_upload, scan_attachment, safe_attachment_bytes


def can_write(user): return user.is_authenticated and role(user) in settings.RULE_AUTHOR_ROLES

def require_author(user):
    if not can_write(user): raise PermissionDenied("규정 문서·규칙 작성 권한이 필요합니다.")

def require_approver(user):
    if not user.is_authenticated or role(user) not in settings.RULE_APPROVER_ROLES: raise PermissionDenied("규정 검토·승인 권한이 필요합니다.")


def documents_for(user):
    qs=RegulationDocument.objects.all()
    if not user.is_authenticated: return qs.none()
    if role(user)=="ADMIN": return qs
    if can_write(user): return qs.filter(Q(visibility="TEAM")|Q(uploaded_by=user))
    return qs.filter(visibility="TEAM",review_status="REVIEWED",scan_status="PASSED",chunks__citations__rule__state__in=["APPROVED","EFFECTIVE","RETIRED"]).distinct()


def tokens(text):
    words=re.findall(r"[a-z0-9가-힣]+",unicodedata.normalize("NFKC",text).casefold())
    output=[]
    for word in words:
        output.append(word)
        if re.fullmatch(r"[가-힣]{3,}",word): output.extend(word[n:n+2] for n in range(len(word)-1))
    return output


@transaction.atomic
def register_document(document,user):
    require_author(user)
    document.uploaded_by=user; document.original_name=normalized_name(document.file.name)
    _,digest=validate_upload(document.file); document.sha256=digest
    document.full_clean(); document.save()
    scan_attachment(document,user)
    audit(user,"REG_DOC_REGISTER",document,after={"sha256":digest,"edition":document.edition,"jurisdiction":document.jurisdiction,"scan_status":document.scan_status})
    return document


@transaction.atomic
def extract_document(document,user):
    require_author(user)
    document=documents_for(user).select_for_update().get(pk=document.pk)
    if document.chunks.exists():
        safe_attachment_bytes(document)
        return document  # Never overwrite an index referenced by an old review.
    if document.scan_status!="PASSED":
        document.extraction_status="BLOCKED";document.extraction_note="파일 검사 통과 후 추출할 수 있습니다."
        document.save(update_fields=["extraction_status","extraction_note","updated_at"]);return document
    try:
        data=safe_attachment_bytes(document)
        if Path(document.file.name).suffix.lower()==".pdf":
            reader=PdfReader(io.BytesIO(data),strict=True)
            if len(reader.pages)>settings.REGULATION_MAX_PAGES: raise ValidationError("문서 페이지 수 제한을 초과했습니다.")
            pages=[(number,page.extract_text() or "") for number,page in enumerate(reader.pages,1)]
        else: pages=[(None,data.decode("utf-8-sig"))]
        empty=[number for number,text in pages if not text.strip()]
        sequence=0;section="";chunks=[]
        for page,text in pages:
            # A heading may follow a single line break in PDF extraction. Split there
            # before assigning locations so a later Article/제N조 never inherits the prior section.
            positioned=re.sub(r"(?m)^(?=\s*(?:제\s*\d+\s*[조장절]|Article\s+\d+|Chapter\s+\d+|§\s*\d+))","\n\n",text)
            paragraphs=[part for part in re.split(r"\n\s*\n",positioned) if part.strip()]
            for paragraph,part in enumerate(paragraphs,1):
                heading=next((line.strip() for line in part.splitlines() if re.match(r"\s*(제\s*\d+\s*[조장절]|Article\s+\d+|Chapter\s+\d+|§\s*\d+)",line,re.I)),None)
                if heading: section=heading[:240]
                normalized=re.sub(r"\s+"," ",part).strip()
                for offset in range(0,len(normalized),880):
                    content=normalized[offset:offset+1000]
                    if not content: continue
                    sequence+=1
                    if sequence>settings.REGULATION_MAX_CHUNKS: raise ValidationError("문서 청크 수 제한을 초과했습니다.")
                    chunks.append(RegulationChunk(document=document,sequence=sequence,page=page,section=section,paragraph=paragraph,text=content,content_hash=hashlib.sha256(content.encode()).hexdigest(),search_tokens=tokens(content)))
        RegulationChunk.objects.bulk_create(chunks)
        document.extraction_status="OCR_REQUIRED" if empty else "READY"
        document.extraction_note=("텍스트 없는 페이지가 있습니다. OCR 필요: "+", ".join(str(p or "본문") for p in empty)[:200]) if empty else f"{sequence}개 청크 색인 완료 · OCR은 자동 수행하지 않습니다."
    except PermissionDenied: raise
    except Exception:
        document.extraction_status="FAILED";document.extraction_note="추출에 실패했습니다. 파일 형식·페이지 수를 확인하세요."
    document.save(update_fields=["extraction_status","extraction_note","updated_at"])
    audit(user,"REG_DOC_EXTRACT",document,after={"status":document.extraction_status,"chunks":document.chunks.count()})
    return document


@transaction.atomic
def review_document(document,user,decision,reason):
    require_approver(user)
    if not reason.strip(): raise ValidationError("문서 검토 사유를 입력하세요.")
    document=documents_for(user).select_for_update().get(pk=document.pk)
    if decision not in ("REVIEWED","REJECTED"): raise ValidationError("올바른 문서 검토 결정을 선택하세요.")
    if decision=="REVIEWED":
        safe_attachment_bytes(document)
        if document.extraction_status!="READY" or not document.chunks.exists(): raise ValidationError("추출 완료된 문서만 검토 완료할 수 있습니다. 스캔 PDF는 OCR이 필요합니다.")
    before={"review_status":document.review_status}
    document.review_status=decision;document.reviewed_by=user;document.reviewed_at=timezone.now();document.review_reason=reason
    document.save(update_fields=["review_status","reviewed_by","reviewed_at","review_reason","updated_at"])
    audit(user,"REG_DOC_REVIEW",document,before,{"review_status":decision,"reason":reason})
    return document


def search_evidence(user,query,jurisdiction="",device_id=None,edition="",as_of=None,document_id=None,limit=20):
    if not user.is_authenticated: raise PermissionDenied
    if (not query or not tokens(query)) and not document_id: return []
    docs=documents_for(user).filter(scan_status="PASSED",extraction_status="READY")
    if jurisdiction: docs=docs.filter(jurisdiction=jurisdiction)
    if device_id: docs=docs.filter(Q(device_id=device_id)|Q(device__isnull=True))
    if edition: docs=docs.filter(edition=edition)
    if document_id: docs=docs.filter(pk=document_id)
    if as_of: docs=docs.filter(Q(effective_on__lte=as_of)|Q(effective_on__isnull=True))
    # The persisted token index remains portable across SQLite/PostgreSQL. No external AI is used.
    index=RegulationChunk.objects.filter(document__in=docs).select_related("document").order_by("pk")
    if index.count()>settings.REGULATION_SEARCH_CHUNKS: raise ValidationError("검색 색인 범위를 초과합니다. 문서·관할·버전 필터로 범위를 좁히세요.")
    chunks=list(index)
    terms=set(tokens(query));frequency=Counter(term for chunk in chunks for term in terms if term in set(chunk.search_tokens))
    scored=[]
    for chunk in chunks:
        tf=Counter(chunk.search_tokens)
        score=sum(math.log(1+(len(chunks)+1)/(frequency[t]+1))*tf[t]/(tf[t]+1.2) for t in terms if tf[t])
        if not terms and document_id: score=1
        if score: scored.append((score,chunk))
    scored.sort(key=lambda x:(-x[0],x[1].document_id,x[1].sequence))
    result=[];checked={}
    for score,chunk in scored:
        if hashlib.sha256(chunk.text.encode()).hexdigest()!=chunk.content_hash:
            continue
        if chunk.document_id not in checked:
            try: safe_attachment_bytes(chunk.document);checked[chunk.document_id]=True
            except (PermissionDenied,OSError): checked[chunk.document_id]=False
        if checked[chunk.document_id]: result.append({"chunk":chunk,"score":round(score,3)})
        if len(result)>=limit: break
    return result
