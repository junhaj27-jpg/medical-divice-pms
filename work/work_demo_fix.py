from pathlib import Path
p=Path('scripts/verify_impact.py');s=p.read_text(encoding='utf-8').replace('request_complaint_approval(case,author)','request_complaint_approval(case,author,reason="TEST 자료 변경 후 재검토")');p.write_text(s,encoding='utf-8')
