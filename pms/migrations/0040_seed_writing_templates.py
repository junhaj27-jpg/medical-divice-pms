from django.db import migrations

SECTIONS = {'III.A': ['Device Description', 2, 'Device Description'], 'III.B': ['Predicate Comparison', 3, 'Predicates and Substantial Equivalence'], 'III.C': ['Labeling / IFU', 3, 'Labeling'], 'III.D': ['Reprocessing', 4, 'Reprocessing'], 'III.E': ['Biocompatibility', 4, 'Biocompatibility'], 'III.F': ['Software', 5, 'Software'], 'III.G': ['Cybersecurity', 6, 'Cybersecurity'], 'III.H': ['Electrical Safety and EMC', 7, 'Electrical Safety and EMC'], 'III.I': ['Wireless Technology', 8, 'Wireless'], 'III.J.1': ['Non-Clinical Performance — Radiant Power', 8, 'Performance Testing'], 'III.J.2': ['Non-Clinical Performance — Heat Generation', 9, 'Performance Testing'], 'IV': ['Modifications', 9, 'Submission context / supporting attachment']}

DENTAL_FIELDS = {
    "use_scope": "사용 범위 (restorative / bleaching / unknown)", "light_source": "광원 (broad_beam / monochromatic / laser)",
    "modes": "작동 모드", "contacts": "환자 접촉 부품", "power": "방사 파워 (mW)", "irradiance": "방사조도 (mW/cm²)",
    "wavelength": "파장 (nm)", "exposure": "노출 시간 (s)", "temperature": "온도 (°C)", "power_supply": "전원",
    "software": "소프트웨어 버전", "wireless": "무선 기능", "reprocessing": "재사용·재처리",
}


def seed_templates(apps, schema_editor):
    Template = apps.get_model("pms", "WritingTemplate")
    Project = apps.get_model("pms", "DentalProject")
    dental_items = [
        {"id": key, "title": value[0], "condition": "changed" if key == "IV" else "always",
         "evidence_type": "Specification / test report / labeling", "source_section": key, "page": value[1],
         "draft_section": value[0], "mapping": value[2]}
        for key, value in SECTIONS.items()
    ]
    common = dict(market="US", pathway="RA verification required", state="PUBLISHED", checked_on="2026-11-14")
    specs = [
        ("dental", "Dental Curing Light", DENTAL_FIELDS, dental_items, False,
         "https://www.fda.gov/media/74206/download", "2026-09-02",
         {"product_codes": ["EBZ"], "regulations": ["872.6070"], "scope": "dental",
          "include": "Restorative resin photopolymerization", "exclude": "Polymerization lasers; bleaching-only"}),
        ("eeg", "DEMO — EEG analysis software", {"inputs": "입력", "outputs": "출력", "software": "소프트웨어 버전",
          "validation": "검증 자료", "users": "사용자", "environment": "사용 환경"},
         example_items([("EEG.IO", "Inputs and Outputs"), ("EEG.SW", "Software Version"), ("EEG.VAL", "Software Verification")]),
         True, "", None, {"include": "예시 뇌파분석 소프트웨어 자료 수집", "exclude": "실제 제출 요건 미확인"}),
        ("monitor", "DEMO — Patient monitoring device", {"measurements": "측정 항목", "sensors": "센서",
          "alarms": "알람 유무", "performance": "성능 자료", "contacts": "환자 접촉", "wireless": "무선 기능"},
         example_items([("MON.SENS", "Sensors and Measurements"), ("MON.ALARM", "Alarms"), ("MON.PERF", "Performance")]),
         True, "", None, {"include": "예시 환자 모니터 자료 수집", "exclude": "실제 제출 요건 미확인"}),
        ("common", "공통 자료 수집", {}, example_items([("COMMON", "Device Information and Evidence")]),
         False, "", None, {"scope": "collection", "include": "분류·경로 미확정", "exclude": "기기별 초안 생성 보류"}),
    ]
    for key, name, fields, items, example, url, issued, conditions in specs:
        Template.objects.get_or_create(key=key, version=1, defaults={
            **common, "name": name, "fields": fields, "items": items, "example": example, "source_url": url,
            "issued_on": issued, "conditions": conditions, "pathway": "510(k)" if key == "dental" else common["pathway"],
        })
    Project.objects.filter(template__isnull=True).update(template=Template.objects.get(key="dental", version=1))


def example_items(rows):
    return [{"id": key, "title": title, "condition": "always", "evidence_type": "DEMO evidence",
             "source_section": "DEMO — RA 확인 필요", "page": 0, "draft_section": title, "mapping": "RA 확인 필요"}
            for key, title in rows]


class Migration(migrations.Migration):
    dependencies = [("pms", "0039_writing_templates")]
    operations = [migrations.RunPython(seed_templates, migrations.RunPython.noop)]
