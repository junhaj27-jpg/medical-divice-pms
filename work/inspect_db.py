import sqlite3
from pathlib import Path
for p in [Path('../independent-empty.sqlite3'),Path('.test-tmp/final-empty.sqlite3')]:
    if p.is_file():
        with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as db:
            names=[r[0] for r in db.execute("select name from sqlite_master where type='table'")]
            print(str(p),'tables',len(names))
            if 'django_migrations' in names: print('pms migrations',list(db.execute("select name from django_migrations where app='pms'")))
