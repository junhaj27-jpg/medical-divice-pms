"""Native PostgreSQL tools; restoration always targets a newly created scratch DB."""
import os
import subprocess
import uuid
from django.conf import settings
from django.core.management.base import CommandError


def pg_environment(database=None):
    config=settings.DATABASES['default'];env=os.environ.copy()
    for envkey,key in [('PGHOST','HOST'),('PGPORT','PORT'),('PGUSER','USER'),('PGPASSWORD','PASSWORD'),('PGDATABASE','NAME')]:
        if config.get(key): env[envkey]=str(config[key])
    if database: env['PGDATABASE']=database
    return env


def run_native(argv,database=None):
    try:
        subprocess.run(argv,env=pg_environment(database),check=True,capture_output=True,timeout=600)
    except (OSError,subprocess.SubprocessError) as exc:
        # Do not echo server output, DSNs, environment, or credentials.
        raise CommandError('PostgreSQL 도구 실행 실패: pg_dump/pg_restore 설치·접속·권한을 확인하세요.') from exc


def dump_postgres(path):
    run_native(['pg_dump','--format=custom','--no-owner','--no-privileges','--file',str(path)])


def verify_postgres(path,manifest,destination):
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc: raise CommandError('psycopg가 필요합니다.') from exc
    config=settings.DATABASES['default']
    kwargs={out:config[key] for out,key in [('host','HOST'),('port','PORT'),('user','USER'),('password','PASSWORD'),('dbname','NAME')] if config.get(key)}
    scratch='pms_verify_'+uuid.uuid4().hex
    created=False
    try:
        with psycopg.connect(**kwargs,autocommit=True) as admin:
            try:
                admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(scratch)));created=True
                run_native(['pg_restore','--no-owner','--no-privileges','--exit-on-error','--dbname',scratch,str(path)],scratch)
                with psycopg.connect(**{**kwargs,'dbname':scratch}) as restored:
                    for table,count in manifest['counts'].items():
                        actual=restored.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]
                        if actual!=count: raise CommandError('복구 DB 행 수 불일치')
                    for table,columns in [('pms_attachment',['file']),('pms_reportartifact',['file','bundle']),('pms_regulationdocument',['file'])]:
                        if table not in manifest['counts']: continue
                        for column in columns:
                            for (name,) in restored.execute(sql.SQL('SELECT {} FROM {}').format(sql.Identifier(column),sql.Identifier(table))):
                                if name and 'media/'+name not in manifest['files']: raise CommandError('복구 DB 참조 파일 누락')
                    # PostgreSQL restores and validates FK constraints by default; any failure above is fatal.
            finally:
                if created:
                    if not scratch.startswith('pms_verify_') or scratch==config['NAME']: raise CommandError('격리 DB 이름 검증 실패')
                    admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(scratch)))
    except CommandError: raise
    except Exception as exc: raise CommandError('격리 PostgreSQL 복구 검증 실패. 운영 DB는 복원 대상으로 사용하지 않습니다.') from exc
    return scratch
