def software_summary(case):
    if case.device.product_type != "SOFTWARE":
        return None
    checks = []
    for capa in case.capas.all():
        evaluation = capa.evaluations.select_related("fixed_release").first()
        checks.append({
            "capa_id": capa.pk,
            "capa": capa.title,
            "release": evaluation.fixed_release.version if evaluation and evaluation.fixed_release else "",
            "verdict": evaluation.get_verdict_display() if evaluation and evaluation.fixed_release else "버전 검증 미완료",
            "result": evaluation.action_result if evaluation else "",
            "evidence": list(evaluation.evidence.order_by("pk").values_list("original_name", flat=True)) if evaluation else [],
        })
    return {
        "intake": case.intake_release.version if case.intake_release_id else "버전 미확인",
        "affected": list(case.affected_releases.values_list("version", flat=True)),
        "rationale": case.impact_rationale,
        "checks": checks,
    }
