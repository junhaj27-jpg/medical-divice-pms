"""Run reproducible validation using a NEW isolated directory; never migrate source DB."""
import argparse, hashlib, json, os, sqlite3, subprocess, sys
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('destination')
parser.add_argument('--installed-db',type=Path)
args=parser.parse_args()
root=Path(args.destination).resolve()
if root.exists(): raise SystemExit('새 격리 디렉터리를 지정하세요.')
root.mkdir(parents=True)
repo=Path(__file__).resolve().parent.parent
base=os.environ.copy()
base.update(DB_ENGINE='sqlite',SQLITE_PATH=str(root/'fresh.sqlite3'),PRIVATE_MEDIA_ROOT=str(root/'media'),STATIC_ROOT=str(root/'static'),PYTHONIOENCODING='utf-8',DJANGO_SETTINGS_MODULE='config.settings')
results=[]
def run(label,argv,env=None):
    with (root/(label+'.log')).open('w',encoding='utf-8') as log:
        proc=subprocess.run([sys.executable,*argv],cwd=repo,env=env or base,stdout=log,stderr=subprocess.STDOUT)
    results.append(dict(label=label,command=argv,exit_code=proc.returncode))
    print(label,proc.returncode,flush=True)
    (root/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    return proc.returncode
for label,argv in [
 ('check',['manage.py','check']),('makemigrations',['manage.py','makemigrations','--check','--dry-run']),
 ('plan',['manage.py','showmigrations','--plan']),('fresh-migrate',['manage.py','migrate','--noinput']),
 ('test',['manage.py','test','--noinput']),('collectstatic',['manage.py','collectstatic','--noinput']),
 ('compile',['-m','compileall','-q','pms','config','scripts'])]: run(label,argv)
prod=base.copy();prod.update(DEBUG='False',SECRET_KEY='validation-only-'+hashlib.sha256(os.urandom(32)).hexdigest(),SECURE_COOKIES='True',SECURE_SSL_REDIRECT='True',SECURE_HSTS_SECONDS='31536000',SECURE_HSTS_PRELOAD='True',ALLOWED_HOSTS='validation.invalid')
run('deploy',['manage.py','check','--deploy'],prod)
if args.installed_db:
    source=args.installed_db.resolve()
    if not source.is_file(): raise SystemExit('설치 DB 경로가 없습니다.')
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    target=root/'forward.sqlite3'
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(target) as dst: src.backup(dst)
    def counts():
        with sqlite3.connect(target) as db:
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'pms_%'")]
            return {t:db.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0] for t in tables}
    old=counts()
    if not old: raise SystemExit('설치 스키마가 없습니다. 0바이트 파일은 전진 적용 근거가 아닙니다. 설치된 DB를 지정하세요.')
    forward=base.copy();forward['SQLITE_PATH']=str(target)
    run('forward-plan',['manage.py','showmigrations','--plan'],forward)
    run('forward-migrate',['manage.py','migrate','--noinput'],forward)
    new=counts();unchanged=all(new.get(k)==v for k,v in old.items())
    preserved=hashlib.sha256(source.read_bytes()).hexdigest()==before
    (root/'forward-preservation.json').write_text(json.dumps(dict(existing_table_count=len(old),row_counts_preserved=unchanged,source_file_unchanged=preserved),indent=2),encoding='utf-8')
    if not unchanged or not preserved: raise SystemExit('원본 또는 기존 행 수 보존 검증 실패')
raise SystemExit(1 if any(r['exit_code'] for r in results) else 0)
