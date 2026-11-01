# MedWatch PMS 실제 검증 보고서

검증일: 2026-11-01 (Asia/Seoul). 이 파일은 시작 시 존재하지 않아 이번 실행 로그로 새로 작성했다. 규제 적합성·법정 기한·의료적 인과관계·성능을 추정하거나 보증하지 않는다. 별도 독립 검증 에이전트는 사용하지 않았다.

## 작업 대상과 보존

- 실제 저장소: `C:\Users\정준하\Documents\Codex\2026-10-30\https-github-com-junhaj27-jpg-medical\work\medical-divice-pms`
- 원격: `https://github.com/junhaj27-jpg/medical-divice-pms.git`
- 시작 HEAD: `14f4390` (반영완료). 최신 로그와 원격을 로컬에서 확인했다. fetch/push·배포는 수행하지 않았다.
- 작업 브랜치: `feature/pms-analysis-snapshots-20261101`.
- 시작 시 README·개발 계획·시연 문서, models/api/regulatory/reporting/services/views/urls/workflow, 관련 템플릿·테스트·requirements가 수정되어 있었으며 0011·0012 및 독립/보고서/workflow 보완 테스트와 이전 verification-report가 미추적 상태였다. 이를 삭제·reset·stash·덮어쓰기 하지 않고 확장했다. 시작 당시 상태가 깨끗했다고 보고하지 않는다.
- 저장소 및 확인한 상위 경로에 AGENTS.md는 발견되지 않았다. README·OPERATIONS·REGULATORY_GUIDE·IMPACT_APPROVAL_GUIDE·docs/development-plan과 관련 코드를 확인했다.
- 원본 DB·미디어에 migrate/seed/삭제를 실행하지 않았다. 모든 변경 DB는 work 아래 격리 경로다. 테스트 실행 중 임시 테스트 DB는 Django 테스트 러너가 생성·해제했다.

## 기존 구현과 이번 변경

기존 구현: Django 템플릿·서비스 계층·STAFF/RA_QA/ADMIN 권한, 규칙 버전·근거·명시 재적용, 영향 분석과 stale 검사, 연결 업무·알림 dedupe, 승인 내용 해시·차단·재승인, CSV 수집·정제·분석·검토 snapshot, 사건 ReportArtifact 비공개 PDF 버전, 즉시 분석 PDF 생성, AI 별도 worker 프로세스 timeout·크기 제한. AI 프로세스 격리는 새로 구현한 것으로 보고하지 않는다.

이번 구현:

1. 영향 분석 JSON 입력을 선택 사건별 행 폼으로 전환했다. 사건번호·제목·제품·최근 적용 규칙·현재 기한 표시, 검색·상태/실제·샘플 필터·20건 페이지, 관할·오프셋 포함 기준 시각·확인 사유 검증, UTC 저장·사용자/규칙 시간대 구분, 대상 선택과 공통 값 명시 확인을 추가했다. signed 목록 토큰과 DB 유일 제출키로 재전송 중복을 막으며 같은 키에 다른 내용을 보내면 거부한다. 기존 영향 분석 서비스와 명시 재적용 절차를 사용한다.
2. RA_QA·ADMIN이 고른 내부 사건의 필드·건수·내용 해시를 미리보기한 후 별도 스냅샷으로 가져온다. 원본 사건과 CSV를 자동 병합하지 않는다. 원본 ID·사건 버전·내용 해시·담당자·시각·정정 체인을 보존한다. 원문 서술·환자정보는 복제하지 않는다. 같은 원본 버전은 중복 생성하지 않으며 정정본은 새 행이고 기본 집계는 최신 내부 버전만 사용한다.
3. 기본 중대성은 UNKNOWN이다. 기존 serious=False를 비중대로 확정하지 않고 별도 명시 확인자·시각·사유 이력을 저장한다. 확인은 원본 bool을 바꾸지 않으며 승인 내용 해시 범위에 포함해 오래된 승인 사용을 차단한다. 확인/가져오기 감사에는 원문·사유 본문을 기록하지 않는다.
4. 분석 PDF를 비공개 파일로 버전 보관한다. 기존 사건 보고서의 FileField·생성 snapshot·행 잠금 버전·감사 패턴과 기존 ReportLab 생성기를 사용한다. 보고서 ID·버전·작성자·생성 시각·필터·비교 기간·집계 기준·양 기간의 원본/정제 레코드 범위와 내용 해시·검토 당시 상태/의견을 보존한다. 재생성은 새 파일이며 이전 파일을 유지한다. 다운로드 권한·해시 확인과 감사, 샘플 여부·발생률 아님·한글 글꼴 안내를 제공한다. 전자서명은 구현하지 않았다.
5. PostgreSQL 전용 동시 내부 스냅샷 중복·동시 규칙 재적용 테스트를 추가했다. 기존 동시 승인·관련 자료 수정 경합 테스트는 유지했다. CI의 마이그레이션 계획 확인과 운영형 배포 검사 설정을 보완했다. CI는 이번 로컬에서 실제 실행하지 않았다.

## 마이그레이션 그래프 및 데이터 보존

0008 두 파일은 같은 번호의 서로 다른 분기다. analysis 분기 → 0009 → 0010, impact 분기는 기존 미커밋 0011 merge에서 합류하고 0012로 이어진다. 이번 추가는 0013_analysis_snapshots_artifacts_impact_submission 및 0014_impact_submission_key다. 최종 pms leaf는 0014_impact_submission_key 하나다. 기존 migration 파일 이름·의존성은 변경하지 않았다.

- 빈 DB: work/validation-final/fresh.sqlite3에서 전체 migrate 실행.
- 저장소의 기본 db.sqlite3는 시작 시 0바이트였다. 이를 설치 DB 전진 적용 성공 근거로 사용하지 않았다.
- 기존 설치 상태: 상위 work/independent-empty.sqlite3는 0012까지 적용된 기존 격리 설치 DB였다. scripts/verify_forward_migration.py로 읽기 전용 복사 후 work/installed-forward/forward.sqlite3에 0013/0014를 적용했다. 기존 PMS 테이블 45개, 사건 0건. 기존 행 수·값 보존 및 원본 파일 SHA-256 불변을 확인했다.
- 데이터가 있는 전진 적용: 위 0012 설치 사본에 합성 사건 1건과 serious=False 이상사례를 추가한 별도 fixture를 만들었다. 다시 읽기 전용 복사해 work/forward-fixture-result에 전진 적용했다. 기존 PMS 테이블 45개, 합성 사건 1건의 기존 행 수·값과 원본 파일 보존을 확인했다. 실제 운영 데이터 이관 검증으로 확대 해석하지 않는다.
- 보존 증거: installed-forward/preservation.json 및 forward-fixture-result/preservation.json. 원본의 실제 내용은 로그에 출력하지 않았다.

## 실제 명령 결과

Python 3.12.14, Django 5.2.18, Windows PowerShell, SQLite. 이 환경의 python은 PATH에 없어 `.venv\Scripts\python.exe`와 기존 `.deps`의 PYTHONPATH를 사용했다. 한글 PDF는 `C:\Windows\Fonts\malgun.ttf`를 설정했다. 새 설치는 requirements.txt 설치를 사용한다.

| 실행 | 결과 |
|---|---|
| manage.py check | 통과, silenced 0 |
| manage.py makemigrations --check --dry-run | 통과, 모델 변경 누락 없음 |
| manage.py showmigrations --plan | 통과, 그래프와 두 분기 합류 확인 |
| manage.py migrate --noinput | 빈 DB 및 기존 설치 사본/합성 데이터 설치 사본 통과 |
| manage.py test --noinput | 아래 실제 전체 실행 기록 참조 |
| manage.py collectstatic --noinput | 격리 STATIC_ROOT에 통과 |
| python -m compileall -q pms config scripts | 통과 |
| git diff --check | 통과 (줄바꿈 정규화 안내는 오류와 구분) |
| manage.py check --deploy | 별도 운영형 환경 설정에서 통과, silenced 0 |

전체 1차: 186개 실행, 180개 통과, PostgreSQL 전용 6개 skip, 실패/오류 없음. work/validation-20261101/test.log.

최종 전체 재실행: 186개 실행, 180개 통과, PostgreSQL 전용 6개 skip, 실패/오류 없음 (work/validation-final/test.log). 마지막 제출키 내용 일치·기존 CSV 검토키 유지 보완 후 관련 41개 실행은 35개 통과·6개 skip (work/final-affected.log). 미리보기 payload와 해시를 한 번의 읽기로 일치시킨 마지막 보완 후 새 기능 13개 모두 통과 (work/final-preview.log). 마지막 check·makemigrations 검사도 통과했다. 테스트 수를 합산해 서로 다른 테스트 수로 과장하지 않는다. 전체 실행 후의 작은 보완은 해당 모듈 집중 회귀로 재검증했다.

운영형 check --deploy는 DEBUG=False, 별도 긴 임의 검증용 SECRET_KEY, secure cookies, SSL redirect, HSTS·includeSubDomains·preload 및 검증용 호스트를 지정했다. SILENCED_SYSTEM_CHECKS 또는 보안 검사 비활성화를 사용하지 않았다. 실제 TLS·프록시·인증서 운영 확인을 뜻하지 않는다.

## 회귀 검증과 skip

- 새 기능 집중 검사: 19개 중 13개 통과, PostgreSQL 전용 6개 skip.
- 기존 분석/영향 검사 22개 통과.
- 행 입력: 누락·잘못된 오프셋·허용되지 않은 사건·동일 제출과 다른 내용 재전송·공통 값 확인·검색·필터·페이지·UTC 날짜 경계·기한 불변·stale 분석·STAFF 차단.
- 내부 스냅샷: UNKNOWN·최소 필드·원본 불변·중복 방지·수정 후 이전 버전/검토 유지·기본 집계 중복 제외·출처 namespace·샘플 분리·미리보기 변경 차단·명시 확인·승인 차단.
- PDF: 한글 텍스트 구조 추출, 버전 증가·이전 파일 불변·생성 시점 검토 유지·범위 해시·한글 글꼴 미설정 안내·역할/비로그인 차단·다운로드 감사·파일 내용 불일치 차단.
- PostgreSQL 전용 skip 6개: test_duplicate_request_is_serialized, test_first_approval_or_rejection_wins, test_transition_only_once, test_related_writer_cannot_cross_approval_lock, test_internal_snapshot_concurrent_duplicate, test_same_case_concurrent_rule_reapplication.
- skip 사유: actual PostgreSQL required; SQLite cannot verify row locks. psql/pg_ctl/docker 실행 파일 및 PostgreSQL 서비스가 로컬 확인에서 발견되지 않았고 실제 PostgreSQL을 실행하지 않았다. SQLite 결과로 동시성 통과를 주장하지 않는다.
- 초기 추가 테스트에서 Windows tempfile 디렉터리 접근 오류가 발생했다. `.test-media` 아래 UUID 격리 디렉터리로 수정한 후 재검증 통과했다. 기존 테스트 삭제/assertion 약화는 하지 않았다.

## 실제 브라우저 확인

computer-use 도구의 in-app browser에서 127.0.0.1:8765에 연결했다. work/ui-demo-final은 새로 만든 합성 DB/미디어다. 외부 서비스에는 자료를 전송하지 않았다.

1. test-author(RA_QA) 로그인 → 내부 CMP-2 선택 → 필드·1건·UNKNOWN·샘플 미리보기 → 명시 확인 → 새 스냅샷 1건 저장 성공 메시지.
2. 영향 입력에서 CMP-2 검색 → 가상 v1/v2 선택 → 빈 입력 행 오류 확인 → TEST-REGION·오프셋 일시·사유로 분석 #2 생성. 재적용 없이 분석만 생성.
3. 영향 입력 목록의 다음 링크 클릭 → 2/2 페이지와 CMP-21~24 표시 확인.
4. 분석 필터에서 샘플 선택 → 현재 보고 건수 1, 비교 0, 미상 1, INTERNAL 출처 표시 확인.
5. 서버 PDF 보관 버튼 → ANL 보고서 v1 실제 PDF 다운로드 → 비공개 버전 목록에서 v1 확인.
6. test-reporter(STAFF) 로그인 → 보관 PDF·내부 분석·영향 분석 URL에서 접근 권한 없음 표시 확인.

HTML 화면 캡처는 outputs/internal-import-browser.png와 outputs/analysis-pdf-browser.png에 보관했다. PDF는 구조/텍스트와 실제 브라우저 다운로드를 검사했으며 전체 페이지의 인쇄 시각 QA를 수행했다고 주장하지 않는다. Chart.js 모든 상호작용, 모든 브라우저·화면 크기를 검증한 것은 아니다.

## 미검증 및 제한

- 실제 PostgreSQL 동시성, 원격 GitHub Actions, Docker 빌드·부하·성능: 미검증.
- 실제 ClamAV·시그니처 운영: 미검증. 합성 규정 fixture의 검사기와 AI 오류/응답 테스트는 mock이며 실제 운영 성공과 구분한다.
- 외부 AI 공급자·자격증명 연동: 미검증, 이번 개발 필수 조건 아님. 기본 분석·시연은 외부 AI를 호출하지 않는다. 기존 worker 격리는 유지한다.
- 실제 운영 DB·환자 데이터 이관·운영 백업 복원·TLS·규정 적합성: 미검증. 규정·법정 시한·중대성/인과관계의 최종 판단은 담당자 검토 영역이다.
- 대량 비동기 수집/분석은 미구현. 영향 입력과 내부 선택은 20건 페이지, 한 번의 내부 가져오기는 최대 100건이다. 페이지 이동 시 미제출 입력은 유지하지 않는다고 화면에 안내한다.
- ORM 서비스 외 직접 SQL/bulk 변경은 같은 잠금·버전 규약을 따라야 한다. SHA-256과 DB 이력은 전자서명·WORM·DB 관리자 변조 방지 보증이 아니다. 전자서명은 이번 범위 제외.

## 변경 파일과 실행

주요 제품 코드: pms/impact_views.py, impact.py, templates/pms/regulatory/impact_list.html, internal_cohort.py, analysis_models.py, analysis.py, analysis_archive.py, analysis_extension_views.py, analysis_views.py, analysis_reporting.py, approval_integrity.py, models.py, urls.py, 분석 템플릿. 추가 마이그레이션은 0013·0014다.

회귀: pms/test_analysis_extensions.py, pms/test_impact_rows.py, pms/test_concurrency.py. 설정/CI: config/settings.py의 격리 STATIC_ROOT, .github/workflows/ci.yml, .gitignore. 문서: README·OPERATIONS·REGULATORY_GUIDE·IMPACT_APPROVAL_GUIDE·docs/development-plan·docs/analysis-extensions-demo·이 보고서. scripts/verify_impact.py는 기존 재승인 사유 요구에 맞춰 합성 시연 사유를 전달하도록 보완했다. 새 scripts/demo_analysis_extensions.py, validate_isolated.py, verify_forward_migration.py를 제공한다.

설치·PowerShell 명령·한국어 시연·PostgreSQL 별도 검증은 [docs/analysis-extensions-demo.md](docs/analysis-extensions-demo.md)를 따른다. 전달 소스 ZIP이 있는 경우 기존 미커밋 보완도 포함한 전체 작업 트리이며 DB·미디어·비밀·.git·가상환경·실행 로그는 포함하지 않는다.
