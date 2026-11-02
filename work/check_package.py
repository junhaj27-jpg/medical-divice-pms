from pathlib import Path
import zipfile
out=Path(r'C:\Users\정준하\Documents\Codex\2026-11-01\c-users-documents-codex-2026-10\outputs')
for name in ['MedWatch-PMS-source-20261101.zip','validation-logs.zip']:
    with zipfile.ZipFile(out/name) as z:
        assert z.testzip() is None
        if name.startswith('MedWatch'):
            assert not any(n.endswith(('.sqlite3','.pyc')) or '/.git/' in n or '/media/' in n for n in z.namelist())
            assert 'medical-divice-pms/VALIDATION_REPORT.md' in z.namelist()
            assert 'medical-divice-pms/pms/migrations/0014_impact_submission_key.py' in z.namelist()
        print(name,'checked',len(z.namelist()),'files')
