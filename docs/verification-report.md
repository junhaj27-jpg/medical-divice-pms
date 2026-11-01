# 독립 검증 보고서

검증일: 2026-10-30 (Asia/Seoul). 개발 담당과 별도 검증 에이전트가 코드, 권한 경계 및 실행 결과를 점검한다. 이 문서는 이번 실행의 증거만 기록하며 과거 README의 테스트 수를 현재 통과 결과로 사용하지 않는다.

## 검증 환경과 보호 범위

- 원격 저장소를 `work/medical-divice-pms`에 새로 clone. 기존 작업 트리/DB/미디어를 덮어쓰지 않음.
- Windows, Python 번들 런타임. 기본 `python` 명령은 PATH에 없음. 번들 Python과 프로젝트 `.deps`의 `PYTHONPATH`로 검증. `.venv`는 패키지 미설치 상태이며 검증에 사용하지 않음.
- 실제 규정의 법정 기한이나 공휴일을 새로 작성하지 않음. 테스트 규칙은 합성 fixture이며 규제 적합성 판단이 아님.
- PostgreSQL/Docker 실행 명령을 이 환경에서 찾지 못함. PostgreSQL 전용 행 잠금 검증은 로컬 미실행이며 기존 CI job으로 남음.

## 독립 코드 검토에서 확인한 누락

| 문제 | 재현 / 기대 | 시작 시 실제 결과 | 조치 및 재검증 |
|---|---|---|---|
| 업무 완료일 누락 | 업무를 DONE 처리하면 완료일을 저장하고 이력/조회에 표시해야 함 | `WorkTask`에 완료일 필드가 없고 `task_state`에도 없음 | 0012 nullable 완료일 추가 및 상태/재개 이력 구현. 독립 마이그레이션/개발 완료·재개 회귀 테스트 통과. 과거 DONE의 정확한 완료일은 NULL 보존. |
| 회수 POST 재전송 중복 | 같은 요청을 두 번 보내도 한 번만 저장되어야 함 | `RecoveryEntry` 요청 식별키가 없어 용량 이내이면 두 건 생성 가능 | UUID 요청키·unique 제약·동일 요청 재사용 구현. 동일 token 재전송 단일 이력, 다른 데이터 token 재사용 거절 회귀 통과. |

## 실행 결과

아래 실제 실행 결과를 참조한다. 실행하지 않은 PostgreSQL 및 운영 규제 검증은 통과로 간주하지 않는다.

## 검증 범위 매핑

- 기존 회귀: `pms/tests.py`, `test_workflow.py`, `test_regulatory.py`, `test_integrity.py`, `test_validation_hardening.py` 등 전체 discovery.
- 기존 데이터 이관: `test_regulatory_migrations.py`는 0006 합성 사건/규칙/계산 스냅샷을 최신까지 적용하며 원래 기한을 확인. `test_impact_migrations.py`는 0007 승인/첨부 경로/기한 보존을 확인.
- 규칙 보존/재계산: `test_regulatory.py`의 과거 스냅샷, stale preview, 영업일 검증 범위. 실법정 기준 검증 아님.
- 업무 경계/CAPA 재조치/증빙 다운로드: `test_workflow.py`와 개발 회귀 테스트.
- 독립 추가: `pms/test_independent_revision.py`는 비로그인/타직원 POST 우회, 잘못된 수량 타입·0·음수·초과·미래 회수일, 원장 중복/0대상, 저장 수량과 보고서 스냅샷 일치, 타직원 업무 GET/POST, 빈/초과 증빙 파일 검증.
- 동시성: SQLite 실제 스레드 회수 용량 테스트와 PostgreSQL 전용 승인 행 잠금 테스트를 구분 기록.

## 제한 사항

브라우저에서 모든 화면을 직접 클릭한 전수 검증이나 운영 인프라/실제 백신 공급자/실제 규제기관 제출 적합성 검증을 수행했다고 주장하지 않는다. API·Django client 실행 테스트, PDF 구조/텍스트 확인, 코드 검토 범위를 구분한다. 개인정보 저장 정책, 조직별 역할 분리, 운영 배포 검토는 별도이다.

## 2026-10-30 실제 실행 중간 결과

검증용 실행기: 번들 `dependencies/python/python.exe`, `PYTHONPATH`에 기존 로컬 `.deps` 사용. 초기 기본 Python PATH 미등록 및 패키지 누락으로 실행 실패한 뒤, 네트워크 설치 대신 로컬 의존성을 사용하여 재실행했다. 새로운 공급자나 외부 API를 호출하지 않았다.

| 실제 명령 | 결과 |
|---|---|
| `manage.py test pms.test_independent_revision pms.test_workflow_revision --noinput -v 2` | 15개 통과, 4.925초. 독립 추가 7개(신규 필드 기존 데이터 이관 포함), 당시 개발 회귀 8개. 이후 추가 변경은 아래 최종 결과로 확인 |
| `manage.py check` | 통과, 0 issues |
| `manage.py makemigrations --check --dry-run` | 통과, No changes detected |
| `python -m compileall -q pms config scripts` | exit 0 |
| `SQLITE_PATH=../independent-empty.sqlite3 manage.py migrate --noinput` | 빈 SQLite DB 전체 0001→0012 및 Django 기본 마이그레이션 성공 |
| `manage.py collectstatic --noinput` | 160개 static 파일 수집 성공 |
| `SECRET_KEY=<CI 전용 50자 미만 값> DEBUG=False manage.py check --deploy` | exit 0, 경고 5개: HSTS, SSL redirect, 짧은 테스트용 SECRET_KEY, secure session/CSRF cookie. 배포 준비 완료를 의미하지 않음 |

추가 검토: 회수 POST token 필수 변경으로 기존 `test_html_rule_recipient_and_recovery_submissions`가 token 없이 302를 기대하는 회귀 충돌을 발견해 개발 담당에 전달했고, UUID token을 포함하도록 테스트를 갱신했다.


## 수정 후 추가 재검증 및 PDF

- `manage.py test pms.test_report_revision pms.test_workflow_revision --noinput -v 1`: **10개 통과, 1.682초**. 개발 담당이 추가한 필수 마감값 검증 회귀와 총괄의 보고서 포함항목 회귀까지 최신 상태 재검증.
- `git diff --check`: 총괄 실행 exit 0.
- PDF 시각 QA는 총괄이 실행하고 독립 검증 에이전트에 증거를 전달: `.test-tmp/pdf-qa/generate.py`의 장문 한글 설명 140회, 업무 10건, CAPA 원인·조치, 리콜 합계, 승인 이력 합성 fixture로 실제 `build_pdf`를 호출하여 **5페이지** 생성. `pypdf`에서 한글 핵심 항목 4개 추출 확인. bundled Poppler `pdftoppm -scale-to 1000 -png`로 5장 렌더하고 `view_image`로 모두 확인. 한글, 반복 표 헤더, 장문 셀 페이지 분리, 여백/푸터에서 겹침과 잘림 미발견. 비ASCII 경로 관련 `nameToUnicode` 경고 3개가 있었으나 exit 0 및 PNG 정상. 이 시각 QA는 합성 fixture 한정이며 임의 첨부 PDF 전수 검증이 아니다. 검증 에이전트가 직접 육안 재검토한 것으로 주장하지 않는다.
- 총괄 실제 HTTP smoke: `runserver --noreload 127.0.0.1:8879` 후 urllib로 `/` 요청, `/accounts/login/` 리다이렉트 및 최종 HTTP 200 확인. 검증 서버 프로세스 종료 완료. 전체 UI 업무 시연을 브라우저에서 클릭한 결과로 확대 해석하지 않음.
- 사용 로컬 패키지 버전: Django 5.2.18, DRF 3.18.3, reportlab 4.4.10, pypdf 6.14.2, tzdata 2026.5 (총괄 확인).
- 최종 승인 잠금순서 정리 및 API 필드별 오류 보존 수정 후 `manage.py test pms.test_integrity pms.test_safety --noinput -v 1`: **21개 통과, 1.972초**. PostgreSQL 행 잠금 자체는 이 SQLite 실행으로 입증되지 않는다.

## 전체 회귀에서 발견한 문제와 수정 요청

첫 전체 실행 `manage.py test --noinput -v 1`은 **166개, 250.564초, 실패 1 / PostgreSQL 전용 skip 4**였다. 전체 통과로 기록하지 않는다. 당시 discovery 이후 추가된 최신 회귀는 별도 10개/21개 재검증으로 확인했다.

- 재현: `pms.test_validation_hardening.IndependentFindingRegressions.test_closure_unchanged_and_changed_requires_reapproval`. 승인 사건을 ACTION_COMPLETE로 전이 → 설명 변경 → CLOSED 거절 확인 → 변경 사유 없이 재승인 요청.
- 기대: 변경/재검토 사유가 없으면 ValidationError. 사유를 입력한 재요청은 APPROVAL로 재개하고 버전과 감사 이력을 남겨야 함.
- 실제: 사유 없는 요청이 허용됨(`assertRaises` 실패).
- 원인: 기존 미해결 merge conflict를 통합하는 중 `request_complaint_approval`의 ACTION_COMPLETE 재개·사유 검증 branch가 누락됨. 총괄에 수정 요청했다. 수정 후 결과는 아래에 별도 기록한다.

## 최종 수정 정책과 검증 담당 변경

전체 회귀에서 발견된 재승인 결함은 총괄이 수정했다. 변경 사유를 문자열/2000자 이하로 검증하고, 승인 완료 후 자료 변경 또는 조치 완료 상태에서의 재승인에는 비어 있지 않은 변경 사유를 요구한다. ACTION_COMPLETE는 APPROVAL로 재개하여 버전·감사 이력을 남기며 정상 단계 전이를 다시 거쳐야 한다. 변경 없는 유효 승인 중복 요청도 거부한다. API/HTML에서 사유를 전달하고 승인 스냅샷 request_reason과 감사 로그에 보존한다. 승인 결정 사유가 요청 사유를 덮어쓰지 않는다.

기존 test_integrity의 이유 없는 재승인/바로 종료 기대는 test_validation_hardening의 사유 필수/승인 단계 복귀 기대와 상충했다. 사용자 요구인 변경 사유·서버 상태 전이를 보존하는 강화된 정책으로 통합하고 test_integrity를 순차 재승인 흐름으로 조정했다. 하드닝 회귀의 기존 실패 기대는 그대로 유지했다. 개발 에이전트가 요청 사유 보존·중복 거절·빈 사유 거절 3개 회귀를 추가했다.

독립 검증 에이전트는 첫 전체 실행 실패와 재현을 확인한 후 사용량 한도로 종료되었다. 개발 에이전트도 최종 재승인 테스트 수정 후 같은 제한으로 종료되었다. 이후 총괄이 검증 역할을 순차 수행했다. 따라서 아래 최종 재실행은 별도 에이전트가 독립 재확인한 결과가 아니다.

- 총괄: `manage.py test pms.test_validation_hardening pms.test_integrity pms.test_report_revision pms.test_workflow_revision pms.test_independent_revision --noinput -v 1`: **40개 통과, 2.107초**.
- 총괄 최종 `check`: 0 issues, `makemigrations --check --dry-run`: No changes detected, `compileall -q pms config scripts`: exit 0, `git diff --check`: exit 0.

## 최종 전체 재실행 결과

총괄이 수정 완료 상태에서 `PDF_KOREAN_FONT=C:\Windows\Fonts\malgun.ttf`, 격리 SQLITE_PATH를 지정하고 `python -u manage.py test --noinput -v 2`를 실행했다. **171개, 133.662초, OK (skipped=4), exit 0**. 실제 성공 167개, PostgreSQL 전용 4개 미실행이다. 최종 로그는 전달 파일 `verification-final-tests.log`에 보존했다.

- 최초 실패한 `test_closure_unchanged_and_changed_requires_reapproval`를 포함한 전체 회귀가 재통과했다.
- 빈 DB 전체 migrate뿐 아니라 0006/0007 기존 사건·규칙·승인·첨부 경로 보존과 0011→0012 기존 완료 업무·회수 이력/누계 보존을 통과했다.
- `ConcurrentRecoveryTests.test_concurrent_capacity_is_preserved`가 통과했다. SQLite 실제 동시 회수 용량 검사이며 PostgreSQL 행 잠금 검증을 대체하지 않는다.
- 인증/다른 사용자/수정·다운로드·보고서 접근, 업무 기한/이력, CAPA 평가 누락·재조치, 잘못된 수량·날짜·재전송·파일, 규칙 개정 후 기존 기한 보존, 보고서 저장 데이터 일치 관련 테스트가 포함됐다.
- 외부 백신/AI 공급자와 실제 규제기관 법정 기준 검증은 수행하지 않았다. 기존 mock 테스트와 실제 로컬 파일/PDF/HTTP 검사를 구분한다.

미완료 우선순위: PostgreSQL CI 실제 재실행 및 행 잠금 검증, 조직별 운영 권한/백신/HTTPS 설정, 공식 관할 규칙·휴일 검토. 변경 소스만 전달하며 원격 push·배포·기존 사용자 DB 변경은 수행하지 않았다. 테스트 통과가 규제 적합성 검증 완료를 뜻하지 않는다.
