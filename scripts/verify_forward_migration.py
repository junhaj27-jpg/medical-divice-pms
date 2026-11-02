"""Verify forward migration on a read-only copy of an installed SQLite database."""
import argparse, hashlib, json, os, sqlite3, subprocess, sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('destination',type=Path);a=p.parse_args()
source=a.source.resolve();root=a.destination.resolve()
if not source.is_file() or root.exists(): raise SystemExit('설치 DB와 새 대상 경로를 지정하세요.')
root.mkdir(parents=True);target=root/'forward.sqlite3'
before=hashlib.sha256(source.read_bytes()).hexdigest()
with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(target) as dst: src.backup(dst)
def state():
    with sqlite3.connect(target) as db:
        names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'pms_%'")]
        values={n:list(db.execute('SELECT * FROM "'+n+'" ORDER BY rowid')) for n in names}
        return {n:len(v) for n,v in values.items()},values
old,values=state()
if not old: raise SystemExit('설치 스키마가 없습니다. 빈 파일은 전진 적용 검증 대상이 아닙니다.')
env=os.environ.copy();env.update(DB_ENGINE='sqlite',SQLITE_PATH=str(target),PRIVATE_MEDIA_ROOT=str(root/'media'),STATIC_ROOT=str(root/'static'),PYTHONIOENCODING='utf-8')
for label,args in [('plan-before',['showmigrations','--plan']),('migrate',['migrate','--noinput']),('plan-after',['showmigrations','--plan'])]:
    with (root/(label+'.log')).open('w',encoding='utf-8') as log:
        rc=subprocess.run([sys.executable,'manage.py',*args],env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    if rc: raise SystemExit(rc)
new,after=state()
# Columns may be appended; compare the original prefix of every existing row.
preserved=all([tuple(row[:len(prior)]) for row in after[n]]==values[n] for n in old for prior in values[n][:1])
result=dict(existing_table_count=len(old),existing_case_count=old.get('pms_customercomplaint'),row_counts_preserved=all(new[n]==old[n] for n in old),existing_values_preserved=preserved,source_file_unchanged=hashlib.sha256(source.read_bytes()).hexdigest()==before)
(root/'preservation.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if not all(result[k] for k in ('row_counts_preserved','existing_values_preserved','source_file_unchanged')): raise SystemExit(1)
