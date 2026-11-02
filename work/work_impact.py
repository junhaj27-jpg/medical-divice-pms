from pathlib import Path
p=Path('pms/impact.py');s=p.read_text(encoding='utf-8').replace('include_closed=False,inputs=None):','include_closed=False,inputs=None,case_ids=None,submission_key=None):');s=s.replace("    inputs=inputs or {}", "    if submission_key:\n        existing=RegulatoryImpact.objects.filter(submission_key=submission_key).first()\n        if existing:\n            if existing.created_by_id!=user.pk: raise PermissionDenied\n            return existing\n    inputs=inputs or {}")
s=s.replace("set(v)-{'jurisdiction','basis_at'}", "set(v)-{'jurisdiction','basis_at','reason'}")
s=s.replace("include_closed=include_closed,", "include_closed=include_closed,submission_key=submission_key,")
s=s.replace("    if not include_closed: cases=cases.exclude(status='CLOSED')", "    if not include_closed: cases=cases.exclude(status='CLOSED')\n    if case_ids is not None:\n        if set(case_ids)!=set(cases.filter(pk__in=case_ids).values_list('pk',flat=True)): raise ValidationError('허용되지 않은 사건입니다.')\n        cases=cases.filter(pk__in=case_ids)")
s=s.replace("        if not reasons: continue", "        if not reasons:\n            if case_ids is not None: raise ValidationError(f'CMP-{case.pk}: 선택 규칙의 후보 사건이 아닙니다.')\n            continue")
p.write_text(s,encoding='utf-8')
