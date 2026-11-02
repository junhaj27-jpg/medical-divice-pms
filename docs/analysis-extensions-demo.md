# 분석 확장 설치·격리 시연 (2026-11-01)

이 절차는 새 가상 DB만 사용한다. 실제 규정·환자자료·운영 DB를 사용하지 않는다. 개발 브랜치: `feature/pms-analysis-snapshots-20261101`. 시작 시 존재한 미커밋 변경은 보존했다. 원격 push·배포·운영 DB migrate는 수행하지 않았다.

## Windows PowerShell 설치

실제 저장소 디렉터리는 지정 작업 폴더 아래 `work\medical-divice-pms`이다. Python 3.12를 설치한 일반 환경에서는 다음을 사용한다.

```powershell
Set-Location 'C:\Users\정준하\Documents\Codex\2026-10-30\https-github-com-junhaj27-jpg-medical\work\medical-divice-pms'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:SECRET_KEY = '로컬-개발용으로-별도-생성한-충분히-긴-임의값'
$env:ALLOWED_HOSTS = '127.0.0.1,localhost'
$env:DEBUG = 'True'
$env:TIME_ZONE = 'Asia/Seoul'
$env:PDF_KOREAN_FONT = 'C:\Windows\Fonts\malgun.ttf'
```

이 작업 환경의 기존 `.venv`에는 Django가 설치되지 않았고 `.deps`에 의존성이 있어, 실제 검증 시에는 `$env:PYTHONPATH=(Join-Path (Get-Location) '.deps')`도 지정했다. 일반 신규 설치에서는 필요하지 않다. `.env`는 자동 로드되지 않는다.

## 격리 시연 데이터와 실행

매번 존재하지 않는 새 디렉터리를 지정한다. 데모 비밀번호는 사용자가 정한다. 기존 `verify_impact.py`의 가상 규칙·승인 시연을 재사용하고 페이지 이동용 가상 사건 23건을 더 만든다. 스캐너는 **가상 fixture에서만 모의 처리**한다. 외부 AI 호출은 없다.

```powershell
$env:DEMO_PASSWORD = '직접-정한-시연용-비밀번호'
.\.venv\Scripts\python.exe scripts/demo_analysis_extensions.py work/demo-new
$env:DB_ENGINE = 'sqlite'
$env:SQLITE_PATH = (Join-Path (Get-Location) 'work\demo-new\demo.sqlite3')
$env:PRIVATE_MEDIA_ROOT = (Join-Path (Get-Location) 'work\demo-new\media')
$env:STATIC_ROOT = (Join-Path (Get-Location) 'work\demo-new\static')
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8765 --noreload
```

1. `test-author`(RA_QA)로 로그인한다. `/rules/impacts/`에서 사건번호·제목·제품 검색, 상태·실제/샘플 필터, 다음 페이지를 확인한다. 페이지별 입력이며 이동 전 현재 선택을 제출한다.
2. CMP-2를 검색하고 기존 가상 규칙 v1, 새 v2를 선택한다. 사건을 체크하고 빈 값으로 저장하면 행별 오류가 보인다. 관할 `TEST-REGION`, 해당 사건 보고일의 `T00:30:00+09:00`, 확인 사유를 입력한다. 사용자 시간대와 UTC 저장 기준을 확인한다. 날짜는 예시이므로 화면의 실제 가상 사건 날짜를 사용한다.
3. 분석 저장 후 기한이 바뀌지 않는지 확인한다. 실제 적용은 분석 상세에서 사유를 적고 명시적 재적용을 선택해야 한다. 규칙·사건이 바뀐 오래된 분석은 다시 만든다. 공통 값은 대상 선택과 별도 확인 체크가 모두 필요하다.
4. `/analysis/internal/`에서 CMP-2를 선택해 미리보기 한다. 복제 필드·1건·샘플·UNKNOWN을 확인하고 확인 체크 후 가져온다. 같은 선택을 다시 가져오면 새 버전이 생기지 않는다.
5. 중대성 확인 펼치기에서 중대/비중대/미상과 확인 사유를 저장한다. 담당자·시각·사유 이력을 확인한다. 다시 가져오면 정정 버전으로 연결되고 이전 버전은 유지된다. 기존 승인 대상이라면 관련 자료 변경으로 재승인이 필요하다. 원본 AdverseEvent.serious는 바꾸지 않는다.
6. `/analysis/`에서 데이터 구분을 샘플로 하고 해당 보고일을 포함한 기간을 선택한다. 최신 내부 사건 1건만 기본 집계되는지 확인한다. 보고 건수이며 발생률이나 위험도가 아니다. CSV는 자동 병합하지 않는다.
7. 서버 PDF 새 버전 보관을 누른다. 같은 필터로 재생성하면 같은 보고서 ID의 다음 버전이 된다. 이전 파일·필터·비교 기간·원본/정제 범위 해시·생성 시점 검토 이력은 유지된다. 비공개 버전 목록에서 다운로드한다. 한글 TTF가 없으면 안내하며 분석 조회는 유지된다.
8. 로그아웃 후 `test-reporter`(STAFF)로 로그인한다. `/analysis/`, `/analysis/internal/`, `/rules/impacts/`, 분석 PDF URL 접근이 거부되는지 확인한다. 다른 STAFF가 등록한 사건은 보이지 않아야 한다.

## 재현 가능한 검증

아래 스크립트는 새 빈 DB, 별도 미디어·정적 경로에서 요청한 Django 검사를 실행하고 로그와 종료 코드를 남긴다. `--installed-db`는 원본을 읽기 전용으로 열어 복사하며 **복사본에만 migrate**한다. 복사 전후 원본 파일 해시와 기존 테이블 행 수를 비교한다. 원본 데이터나 식별정보는 보고서에 출력하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/validate_isolated.py work/validation-new
# 설치된 DB가 있을 때만 (저장소 기본 db.sqlite3는 이번 시작 시 0바이트였음)
.\.venv\Scripts\python.exe scripts/verify_forward_migration.py 경로/설치된.sqlite3 work/forward-new
# 표준 개별 명령 (반드시 위 격리 환경변수로 DB/미디어/정적 경로를 지정한 셸에서 실행)
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py showmigrations --plan
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py test --noinput
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
.\.venv\Scripts\python.exe -m compileall -q pms config scripts
git diff --check
```

`validate_isolated.py`는 별도 운영형 환경변수(HTTPS redirect·secure cookies·HSTS·긴 임의 검증용 키·DEBUG=False)로 `check --deploy`도 실행한다. 보안 검사를 끄지 않는다. 이 검사가 실제 TLS·웹서버·스캐너 운영 검증을 대체하지 않는다.

PostgreSQL은 운영 DB와 분리한 전용 DB/계정을 준비한 뒤 기존 `IMPACT_APPROVAL_GUIDE.md`의 DB_* 설정으로 `manage.py test pms.test_concurrency --noinput -v 2`를 실행한다. CI 파일 존재와 SQLite skip은 PostgreSQL 성공 근거가 아니다.
