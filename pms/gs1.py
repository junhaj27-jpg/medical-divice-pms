"""The application's fixed (01)/(11)/(21) HRI contract; not a barcode encoder."""
import re
from django.core.exceptions import ValidationError


def valid_gtin14(value):
    if not isinstance(value,str) or not re.fullmatch(r"[0-9]{14}",value):return False
    check=(10-sum(int(ch)*(3 if i%2==0 else 1) for i,ch in enumerate(reversed(value[:13])))%10)%10
    return int(value[-1])==check


def validate_gtin14(value):
    if not valid_gtin14(value):
        raise ValidationError("GTIN-14는 선행 0을 포함한 숫자 14자리와 올바른 체크디지트가 필요합니다.",code="invalid_gtin14")


def human_udi(gtin,manufactured_on,serial):
    validate_gtin14(gtin)
    if not manufactured_on:raise ValidationError("실제 제조일을 확인하세요.")
    if not re.fullmatch(r"[A-Za-z0-9]{1,20}",serial):raise ValidationError("이 화면의 GS1 제조번호는 영문·숫자 1~20자리 범위입니다. 기존 원본은 변경하지 않습니다.")
    return f"(01){gtin}(11){manufactured_on:%y%m%d}(21){serial}"


def compare_label(text,gtin,manufactured_on,serial):
    expected=human_udi(gtin,manufactured_on,serial)
    fields=[("01",gtin),("11",manufactured_on.strftime("%y%m%d")),("21",serial)]
    value=text.strip();format_errors=[]
    if value.startswith("("):
        parts=re.findall(r"\(([0-9]{2,4})\)([^()]*)",value)
        if ''.join(f'({ai}){data}' for ai,data in parts)!=value:format_errors.append("괄호 표기 구조를 확인하세요.")
    else:
        for prefix in ("]C1","]d2"):
            if value.startswith(prefix):value=value[len(prefix):];break
        value=value.strip("\x1d")
        # A decoded scanner string for this exact fixed-order layout. AI (21) is last.
        parts=[(value[:2],value[2:16]),(value[16:18],value[18:24]),(value[24:26],value[26:])]
        if len(value)<27 or "\x1d" in value:format_errors.append("지원하는 스캔 필드 구성은 01·11·21 순서입니다.")
    ai_errors=[];value_errors=[]
    if len(parts)!=3:
        format_errors.append("01·11·21 세 필드의 누락·추가 여부를 확인하세요.")
    else:
        for (ai,wanted),(actual,data) in zip(fields,parts):
            if actual!=ai:ai_errors.append({"field":ai,"expected":ai,"actual":actual})
            if data!=wanted:value_errors.append({"field":ai,"expected":wanted,"actual":data})
    return {"schema":1,"expected_udi":expected,"ai_errors":ai_errors,"value_errors":value_errors,
            "format_errors":format_errors,"valid":not(ai_errors or value_errors or format_errors),
            "barcode_encoded_data":None,"barcode_generation_supported":False}
