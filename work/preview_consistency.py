from pathlib import Path
p=Path('pms/internal_cohort.py');s=p.read_text(encoding='utf-8').replace("    return [dict(data=internal_payload(c), hash=digest(internal_payload(c))) for c in cases]", "    rows=[]\n    for case in cases:\n        payload=internal_payload(case)\n        rows.append(dict(data=payload,hash=digest(payload)))\n    return rows");p.write_text(s,encoding='utf-8')
