# MedWatch PMS 로그인·계정 흐름 변경 보고서

작성일: 2026-11-02 (Asia/Seoul)

## 작업 범위와 사전 확인

실제 Git 루트: `C:\Users\정준하\Documents\Codex\2026-10-30\https-github-com-junhaj27-jpg-medical\work\medical-divice-pms`

지정된 상위 폴더 자체는 Git 저장소가 아니며 위 하위 저장소에서 수정했다. 시작 시 미커밋 변경은 없었고, 저장소와 상위 경로에서 적용할 AGENTS.md는 발견되지 않았다. 기본 Django User·Profile, STAFF/RA_QA/ADMIN, 사건/감사 연결, DB 기반 로그인 제한을 확인하고 유지했다. 운영 DB나 외부 ALPLED 사용자 DB·세션에 연결하지 않았다. 커밋·push·배포는 하지 않았다.

참고 저장소는 현재 채팅 작업 폴더의 `work/alpled-reference`에 별도 복제했다. 참조 커밋: `d5f47f147964ec5850420ad7c4058bbf0afc4731`. 요청한 login.html, users/views.py, models.py, middleware.py를 확인했다. 좌우 로그인 구성과 계정 흐름만 참고하고, ALPLED의 사용자 모델·공통 임시 비밀번호·GET 자동 로그아웃·sessionStorage 스크립트·Tailwind CDN은 가져오지 않았다.

## 구현 결과

- 남색·청록 소개 영역과 로그인 폼의 데스크톱 2단 화면, 모바일 폼 우선 배치. label, 자동완성, 포커스와 오류 안내를 적용했다. 실패 응답에는 비밀번호가 다시 표시되지 않는다.
- 기존 username을 사원번호/기존 아이디로 그대로 인증한다. 신규 사원번호는 문자열로 저장한다. 비활성/없는 계정/잘못된 비밀번호는 같은 실패 문구를 사용한다.
- ADMIN 계정 발급·정보 수정·사유 기반 초기화, 자기 잠금·마지막 활성 관리자 보호와 감사 기록을 추가했다. 기존 시간대 설정을 유지했다.
- 계정별 무작위 임시 비밀번호는 발급 응답에서만 표시되고 24시간 만료를 적용한다. DB에는 Django 해시만 저장하며 평문을 세션·감사 기록에 넣지 않는다. 초기화 사유에는 비밀을 입력하지 않도록 안내한다.
- 신규/초기화 계정은 변경 전 HTML/API/Django 관리자 업무 접근을 차단한다. Basic 인증에도 제한한다. API 오류 코드는 password_change_required / temporary_password_expired다.
- 현재 비밀번호 확인, Django 비밀번호 검증, 변경 후 플래그·만료 해제, 현재 세션 갱신을 적용했다. 초기화 시 기존 세션은 다음 요청에 무효화된다.
- 같은 사이트의 절대 경로만 next로 허용한다. 로그인 반복 목적지는 대시보드로 대체한다. 로그아웃은 CSRF POST만 허용하며 민감한 응답과 로그인 제한 응답에 캐시 방지를 적용했다.
- Django admin의 User/Group/Profile 편집을 제거해 감사·보호 규칙을 우회하지 못하게 했다. 계정 관리는 PMS ADMIN 화면을 사용한다.

## 마이그레이션

`pms/migrations/0020_account_lifecycle.py`: Profile에 department, position, must_change_password(False), temporary_password_expires_at(NULL)을 추가한다. 기존 User, 비밀번호 해시, ID나 사건·감사 FK를 변경하는 데이터 마이그레이션은 없다. 기존 사용자는 변경 강제 대상에서 제외된다.

## 검증 결과

격리 SQLite: `work/account-validation.sqlite3`. 테스트는 Django가 생성한 별도 테스트 DB에서 실행했다.

| 검증 | 결과 |
|---|---|
| manage.py check | 통과, 문제 0 |
| makemigrations --check --dry-run | 통과, 변경 없음 |
| migrate --noinput | 통과, 0020 적용 |
| manage.py test --noinput | 217개 실행, 211 통과, 6 건너뜀, 실패/오류 0 (129.211초) |
| git diff --check | 통과 |
| 신규 인증 테스트 | 8개 통과 (전체 실행에 포함) |
| 브라우저 데스크톱 로그인 | 2단 배치·라벨·포커스 확인 |
| 브라우저 모바일 로그인 | 390×844 폼 우선 배치 확인 |
| 브라우저 최초 변경 화면 | 격리 테스트 계정 로그인 후 변경 화면 진입과 모바일 레이아웃 확인 |

회귀 범위: 기존 staff/raqa/admin 로그인, 0 유지, 비활성/비밀번호 오류/시도 제한, ADMIN 발급·초기화 권한, HTML/API/Basic/admin 우회 차단, 만료·변경 후 정상 접근, 초기화 후 기존 세션 무효화, next 차단, GET 로그아웃 거부와 POST CSRF, 감사·세션 비밀 미기록. 기존 사건 권한 회귀 테스트도 전체 테스트에 포함된다.

첫 전체 실행에서 자기 역할 해제 보호 실패 1건을 발견해 수정했다. PDF 폰트 미설정 오류 3건은 Windows 맑은 고딕 설정 후 재실행하여 해소했다.

미검증: 실제 PostgreSQL 행 잠금/동시성 테스트 6개는 SQLite 환경에서 건너뛰었다. 브라우저에서 새 비밀번호 입력·제출 완료는 직접 수행하지 않았으며, 해당 동작은 자동 회귀 테스트로 검증했다. 운영 환경 배포·실제 데이터 DB 적용은 수행하지 않았다.

## 변경 파일

- `docs/ACCOUNT_AUTH_VALIDATION.md`
- `README.md`
- `config/settings.py`
- `config/urls.py`
- `pms/admin.py`
- `pms/api.py`
- `pms/models.py`
- `pms/security.py`
- `pms/templates/pms/base.html`
- `pms/templates/pms/users.html`
- `pms/urls.py`
- `pms/views.py`
- `static/css/app.css`
- `templates/registration/login.html`
- `pms/account_authentication.py`
- `pms/accounts.py`
- `pms/migrations/0020_account_lifecycle.py`
- `pms/templates/pms/account_error.html`
- `pms/templates/pms/credential_issued.html`
- `pms/test_accounts.py`
- `templates/registration/password_change.html`

주요 로직은 pms/accounts.py와 account_authentication.py에 모았고, 기존 views.py의 계정 관리 구현은 제거하여 경로를 통일했다. README에 운영 방법과 검증 명령을 추가했다.

## Windows PowerShell 실행 명령

```powershell
Set-Location 'C:\Users\정준하\Documents\Codex\2026-10-30\https-github-com-junhaj27-jpg-medical\work\medical-divice-pms'
$env:PYTHONPATH = (Resolve-Path '.deps').Path
New-Item -ItemType Directory -Force -Path 'work' | Out-Null
$env:SQLITE_PATH = Join-Path (Resolve-Path 'work').Path 'account-validation.sqlite3'
$env:PDF_KOREAN_FONT = 'C:/Windows/Fonts/malgun.ttf'
$env:PYTHONIOENCODING = 'utf-8'
$py = '.\.venv\Scripts\python.exe'
& $py manage.py check
& $py manage.py makemigrations --check --dry-run
& $py manage.py migrate --noinput
& $py manage.py test --noinput
git diff --check
```

한글 PDF 테스트에는 PDF_KOREAN_FONT가 필요하다. 현재 체크아웃은 의존성이 .deps에 있어 PYTHONPATH를 설정한다. 일반 설치 환경에서는 python manage.py로 같은 명령을 실행할 수 있다.
