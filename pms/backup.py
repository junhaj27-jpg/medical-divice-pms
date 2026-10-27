"""Maintenance-only DB/media archive and isolated SQLite/PostgreSQL verification."""
import hashlib
import json
import sqlite3
import uuid
import shutil
from contextlib import contextmanager, closing

@contextmanager
def scratch_directory(parent):
    path=parent/(".pms-backup-"+uuid.uuid4().hex)
    path.mkdir()
    try: yield path
    finally: shutil.rmtree(path)

import zipfile
from pathlib import Path, PurePosixPath
from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection


def backup(destination,quiesced=False):
    if not quiesced: raise CommandError("웹·작업자·업로드를 중지한 뒤 --quiesced를 지정하세요.")
    if connection.vendor not in ("sqlite","postgresql"): raise CommandError("지원하지 않는 DB입니다.")
    vendor=connection.vendor
    destination=Path(destination).resolve()
    if destination.exists(): raise CommandError("기존 백업을 덮어쓸 수 없습니다.")
    root=Path(settings.MEDIA_ROOT).resolve()
    if destination.is_relative_to(root): raise CommandError("백업은 미디어 밖에 저장하세요.")
    destination.parent.mkdir(parents=True,exist_ok=True)
    with scratch_directory(destination.parent) as tmp:
        db=Path(tmp)/("database.dump" if vendor=="postgresql" else "database.sqlite3")
        if vendor=="sqlite":
            source=sqlite3.connect(str(settings.DATABASES["default"]["NAME"]))
            target=sqlite3.connect(db)
            try: source.backup(target)
            finally: source.close(); target.close()
        else:
            from .postgres_backup import dump_postgres
            dump_postgres(db)
        files={db.name:db.read_bytes()}
        if root.exists():
            for path in root.rglob("*"):
                if path.is_file():
                    if not path.resolve().is_relative_to(root) or path.is_symlink(): raise CommandError("미디어 심볼릭 링크는 백업할 수 없습니다.")
                    files[f"media/{path.relative_to(root).as_posix()}"]=path.read_bytes()
        manifest={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
        counts={}
        if vendor=="sqlite":
            with closing(sqlite3.connect(db)) as conn:
                for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                    counts[table]=conn.execute('SELECT COUNT(*) FROM "'+table.replace('"','""')+'"').fetchone()[0]
        else:
            with connection.cursor() as cursor:
                for table in connection.introspection.table_names():
                    cursor.execute('SELECT COUNT(*) FROM '+connection.ops.quote_name(table))
                    counts[table]=cursor.fetchone()[0]
        with zipfile.ZipFile(destination,"x",zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json",json.dumps({"format":1,"vendor":vendor,"files":manifest,"counts":counts},sort_keys=True))
            for name,data in files.items(): archive.writestr(name,data)
    return manifest


def restore_verify(archive_path,destination):
    destination=Path(destination).resolve()
    live=Path(settings.MEDIA_ROOT).resolve(); live_db=Path(settings.DATABASES["default"]["NAME"]).resolve()
    if destination.exists() or destination==live_db or destination.is_relative_to(live) or live.is_relative_to(destination) or live_db.is_relative_to(destination):
        raise CommandError("복구 대상은 운영 경로와 분리된 새 디렉터리여야 합니다.")
    with zipfile.ZipFile(archive_path) as archive:
        if len(set(archive.namelist()))!=len(archive.namelist()): raise CommandError("중복 경로가 있습니다.")
        manifest=json.loads(archive.read("manifest.json"))
        if manifest.get("format")!=1: raise CommandError("지원하지 않는 백업 형식입니다.")
        files=manifest["files"]
        if set(archive.namelist())!=set(files)|{"manifest.json"}: raise CommandError("백업 파일 목록 불일치")
        # Validate everything before creating the target directory. Never extractall().
        for name,digest in files.items():
            path=PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or not (name in ('database.sqlite3','database.dump') or name.startswith('media/')): raise CommandError("안전하지 않은 백업 경로")
            if hashlib.sha256(archive.read(name)).hexdigest()!=digest: raise CommandError("백업 해시 불일치")
        destination.mkdir(parents=True)
        for name in files:
            path=destination/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(archive.read(name))
    if manifest.get("vendor","sqlite")=="postgresql":
        from .postgres_backup import verify_postgres
        verify_postgres(destination/"database.dump",manifest,destination)
        for name,digest in files.items():
            if hashlib.sha256((destination/name).read_bytes()).hexdigest()!=digest: raise CommandError("복구 후 파일 불일치")
        return manifest
    with closing(sqlite3.connect(destination/"database.sqlite3")) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or conn.execute("PRAGMA foreign_key_check").fetchall(): raise CommandError("복구 DB 무결성 실패")
        for table,count in manifest["counts"].items():
            if conn.execute('SELECT COUNT(*) FROM "'+table.replace('"','""')+'"').fetchone()[0]!=count: raise CommandError("복구 행 수 불일치")
        for table,columns in (("pms_attachment",["file"]),("pms_reportartifact",["file","bundle"]),("pms_regulationdocument",["file"])):
            if table not in manifest["counts"]: continue
            for column in columns:
                for (name,) in conn.execute(f'SELECT "{column}" FROM "{table}"'):
                    if name and f"media/{name}" not in files: raise CommandError("DB가 참조하는 파일 누락")
    for name,digest in files.items():
        if hashlib.sha256((destination/name).read_bytes()).hexdigest()!=digest: raise CommandError("복구 후 파일 불일치")
    return manifest
