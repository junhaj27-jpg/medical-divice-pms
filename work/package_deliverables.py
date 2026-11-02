from pathlib import Path
import zipfile,shutil,hashlib,json,subprocess
repo=Path.cwd()
out=Path(r'C:\Users\정준하\Documents\Codex\2026-11-01\c-users-documents-codex-2026-10\outputs')
out.mkdir(parents=True,exist_ok=True)
for name in ['VALIDATION_REPORT.md','README.md','OPERATIONS.md','REGULATORY_GUIDE.md','IMPACT_APPROVAL_GUIDE.md']:
    shutil.copy2(repo/name,out/name)
(out/'docs').mkdir(exist_ok=True)
for name in ['analysis-extensions-demo.md','development-plan.md']:
    shutil.copy2(repo/'docs'/name,out/'docs'/name)
shutil.copy2(repo/'docs/analysis-extensions-demo.md',out/'PowerShell-설치-실행-시연.md')
roots=['.github','config','docs','pms','samples','scripts','static','templates']
files=[]
for d in roots:
    files += [p for p in (repo/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')]
files += [repo/n for n in ['.dockerignore','.env.example','.gitignore','Dockerfile','docker-compose.yml','manage.py','requirements.txt','README.md','OPERATIONS.md','REGULATORY_GUIDE.md','IMPACT_APPROVAL_GUIDE.md','VALIDATION_REPORT.md'] if (repo/n).is_file()]
archive=out/'MedWatch-PMS-source-20261101.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(set(files)): z.write(p,Path('medical-divice-pms')/p.relative_to(repo))
logs=['work/validation-final','work/installed-forward','work/forward-fixture-result']
with zipfile.ZipFile(out/'validation-logs.zip','w',zipfile.ZIP_DEFLATED) as z:
    for d in logs:
        for p in (repo/d).glob('*'):
            if p.suffix in ('.log','.json'): z.write(p,Path(Path(d).name)/p.name)
    for n in ['final-affected.log','final-preview.log','final-check.log','final-migrations-check.log','diff-check.log','final-exits.json']:
        p=repo/'work'/n
        if p.exists(): z.write(p,n)
(out/'source-sha256.txt').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n내용 비교용 SHA-256이며 전자서명이 아닙니다.\n',encoding='utf-8')
print(json.dumps({'source_files':len(set(files)),'source_zip_bytes':archive.stat().st_size},ensure_ascii=False))
