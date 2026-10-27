# 운영 및 복구 절차

이 문서는 의료기기 시판 후 감시(PMS) 포트폴리오 프로젝트의 운영 절차다. 실제 법정 보고 기준은 제공하지 않는다.

## 설치와 마이그레이션

Python 3.12, Django 5.2 이상 6 미만을 사용한다. 기존 SQLite/PostgreSQL 구조와 인증을 유지한다.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# .env는 자동으로 로드하지 않는다. 필요한 값을 셸 또는 서비스 환경변수로 설정한다.
$env:PDF_KOREAN_FONT='C:/Windows/Fonts/malgun.ttf'
python manage.py migrate
python manage.py check
python manage.py runserver
```

0005는 기존 데이터를 삭제하지 않고 모델·필드·인덱스·제약조건을 추가한다. 0006은 빈 조건 `{}`를 허용한다. 기존 첨부는 PENDING으로 시작하며 재검사 전 다운로드되지 않는다. 기존 CAPA·리콜 수기 집계를 삭제하거나 새 이력으로 꾸미지 않는다. 기존에 종결된 CAPA는 기존 상태를 보존하며, 다시 저장할 때는 새 종결 검증이 적용된다.

MEDIA_ROOT 기본값은 기존 `media/`를 유지하여 기존 파일 경로가 끊기지 않는다. 개발 서버에서도 MEDIA_URL 정적 제공을 제거했다. 실제 운영에서는 PRIVATE_MEDIA_ROOT를 웹 루트 밖 전용 저장소로 지정하고, 기존 media 파일을 서비스 정지 상태에서 그대로 이관한 뒤 DB 상대경로를 유지한다. 웹 서버·CDN에 media alias를 만들지 않는다. 해당 저장소에서 실행을 금지하고 앱 서비스 계정만 읽기·쓰기가 가능하도록 OS 권한을 설정한다. 보고서도 같은 비공개 루트 아래 저장된다.

## 환경변수

| 변수 | 기본값과 의미 |
|---|---|
| TASK_DUE_SOON_DAYS | 3, 업무 마감 임박 일수 |
| TIME_ZONE | Asia/Seoul, 기본 시간대 |
| PRIVATE_MEDIA_ROOT | 기존 media 디렉터리, 비공개 저장 위치 |
| SQLITE_PATH | 기존 db.sqlite3, 검증·별도 환경에서만 경로 변경 |
| PDF_KOREAN_FONT | 필수 한글 TTF 절대경로. 글꼴 없으면 PDF 생성 거부 |
| ANTIVIRUS_COMMAND | JSON argv 배열, 기본 []: 검사 실패 처리 |
| ANTIVIRUS_TIMEOUT | 60초 |
| MAX_UPLOAD_BYTES | 5242880 |
| MAX_EVIDENCE_PIXELS | 25000000 |
| LOGIN_ATTEMPT_LIMIT | 계정별·IP별 각 10회 |
| LOGIN_WINDOW_SECONDS | 고정 구간 900초, 성공·실패를 포함한 인증 시도 기준 |
| SECRET_KEY / DB_* | 기존 환경변수 사용, 비밀은 별도 비밀 저장소에 보관 |

ClamAV 연결 예시는 `.env.example`에 있다. argv는 운영자가 신뢰하는 실행 파일과 옵션으로만 구성한다. shell=True나 사용자 명령을 사용하지 않는다. 검사 도구의 반환값 0만 통과, 1은 격리, 기타 값·타임아웃·도구 미설치는 실패다. 실제 검사기와 최신 시그니처 운영은 별도로 필요하다. `scan_evidence`는 대기·실패 파일만 재검사하며 격리 파일은 자동 해제하지 않는다.

```powershell
$env:ANTIVIRUS_COMMAND='["C:/Program Files/ClamAV/clamscan.exe","--no-summary"]'
python manage.py scan_evidence
python manage.py notify_deadlines
python manage.py prune_login_buckets
```

스케줄러에서 notify_deadlines를 주기적으로 호출한다. 기존 사건 기한 알림과 신규 업무 알림을 함께 만든다. 신규 업무 알림은 담당자·마감·임박/초과별 DB 유니크 키로 중복을 차단한다. 외부 이메일·문자는 발송하지 않는다. prune_login_buckets는 매일 실행한다.

관리자 사용자 화면에서 IANA 시간대(예: Asia/Seoul, America/New_York)를 변경할 수 있다. DB는 USE_TZ=True의 UTC 저장을 유지한다. 임박 3일은 현재 시각부터 72시간 범위다. 마감 입력·표시는 사용자 시간대로 변환하며 DST의 중복·없는 시각은 폼에서 오류로 처리한다.

## 업무 및 데이터 정책

- 내 할 일: `/tasks/`. STAFF는 본인에게 배정된 본인 접수 사건 업무만 열람하고 상태만 변경한다. RA_QA·ADMIN은 전체 업무를 배정·수정한다. STAFF 배정으로 다른 사건 접근권한이 생기지 않는다.
- 업무는 사건을 필수 연결하고 CAPA 또는 리콜 중 하나를 선택 연결한다. 재조치 담당자는 CAPA owner를 사용하되 사건 접근권한이 없는 STAFF이면 평가자에게 배정한다. 재조치 기한은 생성 시각+임박 기준 일수다.
- CAPA 평가는 추기식이다. 미평가는 평가 이력이 없는 상태다. 평가자·예정일·평가일·결과·기준·판정·근거를 매번 보존한다. 미흡 판정마다 별도 재조치 업무를 만든다. 최신 평가가 적합이고 결과/기준/예정일이 해당 평가와 일치하며 연결 업무가 완료되어야 서비스에서 종결한다.
- CAPA 증빙은 동일 사건의 검사 통과 첨부만 연결할 수 있다. 증빙 다운로드는 사건 접근권한·검사 상태·파일 해시를 다시 확인한다.
- 리콜 상세에서 거래처별 원장으로 이동한다. 제품은 리콜, 로트는 해당 제품으로 제한한다. 대상 원장은 생성 후 식별자·단위·수량을 변경하지 않고 통보·회신만 수정한다. 회수는 별도 이력을 추가하고 잘못된 입력은 음수 회수로 상쇄하지 않는다. 정정 워크플로는 별도 확장이 필요하다.
- 누적 회수는 원장에서 합산한다. DB 예약 카운터는 동시 등록 제어 전용이며 같은 트랜잭션에서 회수 이력을 생성한다. 단위별로 합계와 잔량을 보여준다. 기존 리콜 recovered_quantity 수기 집계는 과거 자료로 유지하며 신규 원장과 합산하지 않는다.
- v1.7 보고 규칙은 RA_QA·ADMIN이 초안을 만들고 ADMIN이 승인·시행한다. 작성자 본인 승인은 기본 차단한다. 자세한 절차는 REGULATORY_GUIDE.md를 따른다. 조건은 AND로 묶인 complaint_type·risk_level·serious의 동등 비교만 허용한다. 코드·수식·eval은 지원하지 않는다. 최신 시행 버전이 조건에 맞지 않으면 구버전으로 되돌아가지 않는다.
- 사건 적용은 사용자가 특정 시행 버전을 명시적으로 선택하고 변경 전후 계산을 확인해야 한다. 시작일 포함·기한 단위·마감 시각·규칙 시간대는 근거 검토 후 입력하며 임의 기본값은 없다. 영업일은 토·일과 해당 버전의 명시적 휴일만 제외하고 확인 기간을 벗어나면 확정하지 않는다. 공휴일 자동 갱신과 실제 법정 규칙 기본 제공은 없다.
- 규칙 변경은 기존 사건 기한을 바꾸지 않는다. RA_QA·ADMIN의 사유 있는 명시적 적용·재적용 때만 새 적용 이력과 사건 due_date를 저장한다. 정확한 시각·시간대는 적용 이력에 보존한다.
- PDF 생성은 POST이며 RA_QA·ADMIN만 가능하다. 새 버전과 생성자·시각·해시·데이터 스냅샷을 보존한다. 미검사·격리·실패 파일은 상태 목록만 남기며 본문·증빙 묶음에서 제외한다. 통과 이미지/PDF만 병합하고 TXT/CSV 등 원본은 증빙 ZIP에 넣는다. 기존 버전에도 동일 권한을 적용한다. 생성 후 포함 증빙이 격리·실패 상태가 되거나 해시가 바뀌면 기존 PDF/ZIP 다운로드도 차단하며 기존 파일 자체는 덮어쓰지 않는다.
- PDF 생성기는 URL/파일 경로를 문서에서 해석하지 않는다. 텍스트는 escape하고 이미지·PDF는 비공개 루트에서 해시를 검증한 메모리 바이트만 사용한다. PDF 페이지의 주석/페이지 액션은 병합에서 제거한다. 글꼴 경로는 운영자 설정만 사용한다.

## 백업: 반드시 쓰기 중지

DB와 파일을 함께 보존하려면 먼저 웹·작업자·업로드·알림·관리 명령을 모두 중지한다. `--quiesced`는 운영자가 중지를 완료했다는 선언이며 프로그램이 다른 프로세스를 자동 중지하지는 않는다. 백업 시작부터 완료까지 쓰기를 다시 허용하지 않는다.

```powershell
python manage.py backup_pms D:/pms-backups/pms-2026-10-27.zip --quiesced
```

SQLite는 sqlite backup API로 DB 스냅샷을 만들고 비공개 파일 전체와 행 수·SHA-256 목록을 ZIP으로 저장한다. PostgreSQL은 환경변수의 DB 연결 정보로 pg_dump custom format을 생성하고 같은 파일 목록을 묶는다. pg_dump는 서버 버전에 맞는 클라이언트가 PATH에 있어야 한다. 백업은 기존 파일을 덮어쓰지 않고 미디어 디렉터리 안에 저장할 수 없다.

백업 ZIP에는 격리 파일과 DB의 인증 데이터도 포함된다. 이 ZIP을 사용자 보고서 증빙 ZIP과 혼동하지 않는다. 운영자만 접근 가능한 암호화 볼륨·백업 저장소에 보관하고 보존기간·접근권한·오프사이트 사본을 별도 정책으로 정한다. 현재 구현은 전체 파일을 메모리에 적재하므로 대규모 데이터에서는 스트리밍/스토리지 스냅샷 기반 확장이 필요하다.

## 격리 복구 검증

```powershell
python manage.py restore_verify_pms D:/pms-backups/pms-2026-10-27.zip D:/pms-verify/new-unique-directory
```

대상은 존재하지 않는 새 디렉터리여야 한다. 라이브 DB/미디어 또는 그 상위·하위 경로를 거부한다. 모든 ZIP 경로와 해시를 먼저 확인한 뒤 직접 파일을 쓰며 extractall을 사용하지 않는다. SQLite는 별도 database.sqlite3로 복구하고 integrity_check·foreign_key_check·테이블별 행 수·참조 파일 존재·파일 해시를 검증한다.

PostgreSQL은 pg_restore와 psycopg가 필요하며 현재 연결 인스턴스에 `pms_verify_<무작위 UUID>`라는 새 DB를 만든다. 운영 DB 이름을 복구 대상으로 사용하지 않는다. 검증 후 자신이 만든 임시 DB만 제거하고 파일 복구 디렉터리는 보존한다. CREATEDB 권한과 테스트 인스턴스 사용을 권장한다. 실패하면 비밀·도구 출력 대신 일반 오류를 반환하며, 장애로 정리가 중단된 경우 해당 무작위 DB를 운영자가 확인한다.

실제 운영 DB를 교체하는 복구 명령은 제공하지 않는다. 격리 검증 결과를 검토한 뒤 별도 승인된 운영 전환 절차를 따른다.

## HTTPS·프록시·로그

운영에서는 DEBUG=False, 실제 ALLOWED_HOSTS, 별도 무작위 SECRET_KEY, HTTPS, Secure Cookies를 적용하고 HTTPS 검증 후 HSTS를 설정한다. 개발 기본값의 check --deploy 경고는 운영 설정을 적용해 해소해야 한다. 로그인 제한은 REMOTE_ADDR를 사용하며 임의 X-Forwarded-For를 신뢰하지 않는다. 리버스 프록시에서 실제 클라이언트 주소를 안전하게 전달하도록 구성한다. DB 카운터이므로 프로세스별 로컬 캐시에 의존하지 않는다. 보안 로그에는 비밀번호·토큰·증빙 본문·검사기 원문 출력을 넣지 않는다.

## 검증 명령

```powershell
python manage.py test -v 2
python manage.py makemigrations --check --dry-run
python manage.py check
python manage.py check --deploy
python manage.py collectstatic --noinput
python -m compileall -q pms config scripts
# 새 전용 디렉터리에만 예시 DB/PDF/백업/격리 복구를 만든다.
python scripts/verify_sample.py D:/pms-verify/new-sample-directory
```

PDF 테스트와 verify_sample 실행에는 PDF_KOREAN_FONT가 필요하다. 환경변수가 없으면 해당 자동 테스트는 skip으로 명시되고 PDF 기능은 성공으로 간주하지 않는다. 예시 검증 스크립트의 검사기는 mock이며 실제 악성코드 검사 결과가 아니다. 실제 검사기 설정은 앱 코드에서 자동으로 우회되지 않는다.
