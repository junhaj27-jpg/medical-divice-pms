import hashlib
import io
import subprocess
import unicodedata
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from PIL import Image


def normalized_name(name):
    value=unicodedata.normalize("NFKC",str(name)).replace("\\","/").split("/")[-1]
    value="".join(c for c in value if c.isprintable() and c not in ':<>"|?*').strip(" .")
    return (value or "attachment")[-255:]


def validate_upload(file):
    if file.size>settings.DATA_UPLOAD_MAX_MEMORY_SIZE: raise ValidationError("첨부 크기 제한을 초과했습니다.")
    suffix=Path(normalized_name(file.name)).suffix.lower()
    file.seek(0); data=file.read(); file.seek(0)
    if not data: raise ValidationError("빈 파일은 허용되지 않습니다.")
    try:
        if suffix==".pdf":
            from pypdf import PdfReader
            if not data.startswith(b"%PDF-"): raise ValueError()
            reader=PdfReader(io.BytesIO(data),strict=True)
            if reader.is_encrypted or not len(reader.pages): raise ValueError()
            kind="pdf"
        elif suffix in (".png",".jpg",".jpeg"):
            with Image.open(io.BytesIO(data)) as image:
                if image.width*image.height>settings.MAX_EVIDENCE_PIXELS: raise ValueError()
                if image.format != ("PNG" if suffix==".png" else "JPEG"): raise ValueError()
                image.verify()
            kind="png" if suffix==".png" else "jpeg"
        elif suffix in (".txt",".csv"):
            text=data.decode("utf-8-sig")
            if any(ord(c)<32 and c not in '\r\n\t' for c in text): raise ValueError()
            if any(x in text.lower() for x in ("<script","<html","<?php","<svg","#!/")): raise ValueError()
            kind="text"
        else: raise ValueError()
    except Exception as exc:
        raise ValidationError("확장자와 실제 형식이 일치하는 PDF·PNG·JPEG·UTF-8 TXT/CSV만 허용됩니다.") from exc
    return kind,hashlib.sha256(data).hexdigest()


def private_path(file):
    root=Path(settings.MEDIA_ROOT).resolve()
    path=Path(file.path).resolve()
    if not path.is_relative_to(root) or not path.is_file(): raise PermissionDenied("허용되지 않는 파일 경로입니다.")
    return path


def scan_attachment(attachment,user=None):
    from .services import audit
    attachment.scan_status="PENDING"; attachment.save(update_fields=["scan_status"])
    try:
        attachment.file.open("rb")
        kind,digest=validate_upload(attachment.file)
        if attachment.sha256 and attachment.sha256!=digest:
            raise ValidationError("등록 당시 원본과 해시가 다릅니다. 원본을 바꾸지 말고 새 문서 버전을 등록하세요.")
        attachment.detected_type=kind; attachment.sha256=digest
        command=settings.ANTIVIRUS_COMMAND
        if not command:
            attachment.scan_status="FAILED"
        else:
            # Trusted operator-configured argv only; never shell-expand file names.
            result=subprocess.run([*command,str(private_path(attachment.file))],shell=False,timeout=settings.ANTIVIRUS_TIMEOUT,capture_output=True)
            attachment.scan_status="PASSED" if result.returncode==0 else "QUARANTINED" if result.returncode==1 else "FAILED"
    except ValidationError: attachment.scan_status="QUARANTINED"
    except Exception: attachment.scan_status="FAILED"
    attachment.file.close()
    attachment.scanned_at=timezone.now()
    attachment.save(update_fields=["scan_status","sha256","detected_type","scanned_at"])
    audit(user,"FILE_SCAN",attachment,after={"status":attachment.scan_status,"sha256":attachment.sha256})
    return attachment


def safe_attachment_bytes(attachment):
    if attachment.scan_status!="PASSED": raise PermissionDenied("검사 통과 파일만 사용할 수 있습니다.")
    data=private_path(attachment.file).read_bytes()
    if not attachment.sha256 or hashlib.sha256(data).hexdigest()!=attachment.sha256: raise PermissionDenied("파일 무결성 검사 실패")
    return data
