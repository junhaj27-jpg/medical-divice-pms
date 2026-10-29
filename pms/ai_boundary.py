"""Isolated approved callable; timeout kills its process, errors never include payloads."""
import json
import os
import subprocess
import sys
import tempfile
from django.conf import settings
from django.core.exceptions import ValidationError


def call_approved(*, system, request, evidence):
    if not (settings.RULE_AI_ENABLED and settings.RULE_AI_APPROVED and settings.RULE_AI_ADAPTER):
        raise ValidationError("AI 연결 필요: 승인된 공급자 설정을 확인하세요.")
    try:
        payload = json.dumps(dict(adapter=settings.RULE_AI_ADAPTER, system=system, request=request, evidence=evidence),ensure_ascii=False).encode()
    except (TypeError,ValueError):
        raise ValidationError("AI 전송 자료 형식이 올바르지 않습니다.") from None
    if len(payload)>settings.RA_AI_MAX_INPUT_BYTES: raise ValidationError("AI 전송 크기 제한을 초과했습니다.")
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    env["PYTHONIOENCODING"] = "utf-8"
    with tempfile.TemporaryFile() as output:
        try:
            with subprocess.Popen([sys.executable,"-m","pms.ai_worker"],cwd=settings.BASE_DIR,env=env,
                                  stdin=subprocess.PIPE,stdout=output,stderr=subprocess.DEVNULL) as proc:
                try: proc.communicate(payload,timeout=settings.RA_AI_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    proc.kill();proc.communicate()
                    raise ValidationError("AI 응답 시간이 초과되었습니다. 로컬 검색을 이용하세요.") from None
                if proc.returncode: raise ValidationError("AI 공급자 오류입니다. 로컬 검색을 이용하세요.")
            if output.tell()>settings.RA_AI_MAX_OUTPUT_BYTES: raise ValidationError("AI 응답 크기 제한을 초과했습니다.")
            output.seek(0)
            response=json.loads(output.read(settings.RA_AI_MAX_OUTPUT_BYTES+1))
        except ValidationError: raise
        except Exception:
            raise ValidationError("AI 응답을 검증하지 못했습니다. 로컬 검색을 이용하세요.") from None
    if not isinstance(response,dict): raise ValidationError("AI 응답은 JSON 객체여야 합니다.")
    return response
