from pathlib import Path
p=Path('.github/workflows/ci.yml');s=p.read_text(encoding='utf-8').replace('      - run: python manage.py migrate --noinput','      - run: python manage.py showmigrations --plan\n      - run: python manage.py migrate --noinput');s=s.replace('env: {SECRET_KEY: "ci-only-long-secret-key", DEBUG: "False"}', '''env:
          SECRET_KEY: "ci-only-not-a-production-secret-key-do-not-use-for-live-deployments-20261101"
          DEBUG: "False"
          SECURE_COOKIES: "True"
          SECURE_SSL_REDIRECT: "True"
          SECURE_HSTS_SECONDS: "31536000"
          SECURE_HSTS_PRELOAD: "True"
          ALLOWED_HOSTS: "ci.invalid"''');p.write_text(s,encoding='utf-8')
p=Path('docs/analysis-extensions-demo.md');s=p.read_text(encoding='utf-8').replace('scripts/validate_isolated.py work/validation-new --installed-db db.sqlite3','scripts/validate_isolated.py work/validation-new\n# 설치된 DB가 있을 때만 (저장소 기본 db.sqlite3는 이번 시작 시 0바이트였음)\n.\\.venv\\Scripts\\python.exe scripts/verify_forward_migration.py 경로/설치된.sqlite3 work/forward-new');p.write_text(s,encoding='utf-8')
