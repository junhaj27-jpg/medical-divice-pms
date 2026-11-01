<!-- tracking-current-guide -->
> **2026-11-01 · 6~9순위 현재 안내**: [설계](TRACKING_DESIGN.md), [구현·검증](TRACKING_VALIDATION.md), [문서 비교 후 수정·검증 범위](TRACKING_REVIEW_FIXES.md)를 우선 확인하세요. 현재 마이그레이션 leaf는 `0018_duplicate_review`입니다. 아래 계획·구현 표·최신 기록 표시는 각 이전 단계 당시의 기록입니다.

# 2026-11-01 구현 현황 갱신

지정 폴더 아래 work/medical-divice-pms 저장소를 확인했다. 시작 HEAD는 14f4390이며 README·모델·서비스·workflow·테스트와 0011/0012 등 기존 미커밋 변경을 보존했다. 별도 feature/pms-analysis-snapshots-20261101 브랜치에서 확장한다. AGENTS.md는 확인한 저장소·작업 상위 경로에서 발견되지 않았다.

| 항목 | 결과 | 구현 |
|---|---|---|
| AI 프로세스 격리 | 기존 구현 유지 | ai_boundary.py가 ai_worker 프로세스 종료·timeout·입출력 제한 적용 |
| 영향 분석 서비스·승인 무결성 | 기존 구현 유지·확장 | 오래된 분석 차단, 적용/제외 사유, 연결 업무·알림 dedupe, 승인 내용 해시 |
| 영향 분석 행 입력 | 추가 | impact_views.py, impact_list.html: 검색·필터·20건 페이지·행 검증·공통 값 명시 확인·UTC 저장·제출키 |
| 내부 사건 코호트 | 추가 | internal_cohort.py: 미리보기 해시 검증, 원본 사건 잠금, 출처 분리, 최소 필드·확인 중대성·정정 체인·최신 집계 |
| 분석 PDF 버전 보관 | 추가 | analysis_archive.py: 기존 사건 PDF의 비공개 FileField·내용 snapshot·행 잠금 버전·감사 패턴 사용 |
| 마이그레이션 | 추가만 | 두 0008 분기는 기존 0011에서 병합, 0012 뒤 0013·0014 추가. 기존 파일 이름·의존성 변경 없음 |
| 회귀·동시성 | 확장 | test_analysis_extensions.py, test_impact_rows.py, test_concurrency.py. 실행 결과는 ../VALIDATION_REPORT.md |
| 재현 가능한 검증·시연 | 추가 | scripts/validate_isolated.py, demo_analysis_extensions.py, analysis-extensions-demo.md |

남은 범위: 실제 PostgreSQL 동시성 실행, 대용량 비동기 작업, 운영 ClamAV·TLS·백업복원 실증, 승인된 외부 AI 공급자 연동 검증. 전자서명·외부 불변 저장소는 미구현이며 이번 범위 제외. 법정 기한·인과관계·규제 적합성을 확정하지 않는다.

아래는 당시 작업 기록이며 최신 테스트 수와 구현 상태는 위 표 및 VALIDATION_REPORT.md를 우선한다.

---

# 현황 분석 및 추가 개발 계획 (2026-10-30)

## 작업 경계와 역할
저장소를 새 작업 폴더에 clone했으며 시작 시 git status는 깨끗했다. 저장소와 상위 작업 경로에 AGENTS.md는 발견되지 않았다. 원격 push·배포·서비스 내부 LLM 에이전트 서버 추가는 하지 않는다. 기존 DB·미디어는 가져오거나 수정하지 않는다. 총괄은 병합 충돌 해소·보고서·문서, 개발 에이전트는 workflow 모델·서비스·화면·회귀 테스트, 독립 검증 에이전트는 별도 테스트·실행 검사·검증 보고서를 소유한다.

## 현황 (기존 코드 확인 기준)
| 항목 | 판단 | 실제 경로와 근거 |
|---|---|---|
| 의료기기·이상사례 등록 및 조회 | 구현됨 | pms/models.py MedicalDevice/CustomerComplaint/AdverseEvent, pms/forms.py, pms/views.py, pms/api.py, pms/urls.py의 목록·상세·등록 경로 |
| 업로드·입력 검증·중복 판별 | 구현됨 | pms/file_security.py 실제 파일 형식·크기·검사·비공개 읽기; pms/analysis.py CSV 행 검증 및 출처 ID/해시 중복; pms/serializers.py 모델 연결 검증 |
| 기간별·기기별 통계·위험 신호 | 구현됨 | pms/analysis.py 비교 기간 통계, pms/safety.py 신호 규칙, pms/safety_views.py 권한별 검토; 분모 없는 발생률은 제공하지 않음 |
| 규정 근거·보고 규칙 버전 | 구현됨 | pms/regulatory.py 초안·검토·승인·시행·폐기/명시 재적용, pms/regulation_documents.py 원문 chunk, pms/impact.py 개정 영향, RuleApplication.snapshot 과거 계산 보존 |
| 담당 업무·기한 | 부분 구현 | pms/workflow.py save_task/notify_tasks, pms/workflow_views.py 내 업무·임박·초과 필터, WorkTask/TaskHistory; 완료일 필드 누락 → 이번 추가 |
| CAPA·효과성 평가 | 구현됨 | CAPA/CAPAEvaluation, pms/workflow.py evaluate_capa/close_capa: 미흡 시 재조치 업무, 평가/증빙/미완료 업무 종료 차단 |
| 리콜 통보·회신·회수 이력 | 부분 구현 | RecallRecipient/RecoveryEntry/RecallContact, pms/workflow.py; 수량 제약·원장 존재, stale 객체 counter 덮어쓰기 및 재전송 누락 → 이번 보완 |
| AI 분석·원문 근거 | 구현됨 | pms/rule_ai.py, pms/ra_assistant.py, pms/ai_boundary.py; 인용 검증·선택형 어댑터. 별도 LLM 서버 추가는 적용 불필요 |
| 보고서 출력 | 부분 구현 | pms/reporting.py 비공개 PDF/ZIP·버전 스냅샷, pms/analysis_views.py CSV BOM/수식 방어; 완료일·원인/조치·검토 이력·조건 연결 보완 |
| 인증·권한·감사 | 부분 구현 | pms/services.py visible_complaints/audit, pms/permissions.py, pms/security.py, 다운로드 접근 검사. 승인 로직 병합 충돌로 실행 불가 → P0 수정 |
| 테스트·CI | 부분 구현 | pms/test_*.py, pms/tests.py, .github/workflows/ci.yml SQLite·PostgreSQL 검사. 7개 파일 충돌 표시와 두 migration leaf로 실행 차단 → P0 통합 |

## 구현 우선순위와 결과
1. P0: pms/api.py, models.py, regulatory.py, services.py, urls.py, views.py, templates/pms/complaint_detail.html의 커밋된 충돌을 통합한다. 기존 안전 신호·분석과 개정 영향 기능을 함께 보존하고 승인 스냅샷은 pms/approval_integrity.py의 버전형 구현을 일원화한다. API/HTML 이름 충돌 회피와 권한 예외 처리를 유지한다. 재승인 변경 사유와 승인 단계 복귀·순차 진행을 서버에서 검증하고 요청 사유를 스냅샷/감사 이력에 보존한다. 0011 merge로 기존 migration 파일은 수정하지 않는다.
2. P1: WorkTask.completed_at은 서버에서 완료/재개 시 처리하고 TaskHistory에 보존한다. 과거 DONE의 실제 완료 시각은 추측하지 않고 NULL로 둔다. 리콜 metadata 수정은 DB의 최신 recovered_total을 유지한다. 통보/회신 날짜와 미회수 사유, 미래 회수/연락 입력을 검증한다. 새 회수 화면은 UUID 요청키로 재전송 중복을 막고 기존 원장에는 NULL을 유지한다. 0012는 추가 필드만 적용한다.
3. P2: 기존 PDF 생성기를 확장해 사건 조회 조건·생성시각, 업무 완료일, CAPA 원인/시정/예방 조치, 규칙 개정 검토 및 관리자 결정 이력을 보존한다. 규칙 법정 기한이나 공휴일은 새로 만들지 않는다. 공식 근거 확인은 별도 담당자 검토로 남긴다.

## 검증 및 한계
최종 전체 테스트 171개 중 167개 통과, PostgreSQL 전용 4개 skip. 실제 명령과 결과는 docs/verification-report.md가 최신 기록이다. 기존 문서의 테스트 개수는 과거 기록이다. PostgreSQL 동시성·PDF 시각 검증 등 실행하지 않은 항목을 통과로 간주하지 않는다. 테스트 성공은 규제 적합성 검증과 다르다. 외부 메시지·실제 규정 자동 수집·새 프레임워크는 추가하지 않는다.

## 후속 우선순위
PostgreSQL에서 동시 회수/승인 잠금 재검증, 장문 PDF의 시각 회귀, 운영 파일 검사기·HTTPS·비밀키 설정, 관할별 공식 규정과 휴일의 책임자 검토를 우선한다. 과거 완료일 보완은 검증된 자료에 의한 별도 이관 절차가 필요하다.

---
## 이전 개발 기록 (당시 기록 보존)

# PMS 분석 추가 개발 계획

2026-10-28. 기존 목적은 의료기기 PMS·리콜 포트폴리오 데모. Django 5.2 / DRF / SQLite(PostgreSQL 선택), 서버 템플릿을 유지한다. 작업 시작 git status는 깨끗함. 저장소와 상위 작업 폴더에 AGENTS.md 없음.

## 사전 확인과 우선순위
| 후보 | 시작 상태 | 근거 / 결정 |
|---|---|---|
| 인증·권한·사건 입력 | 구현됨 | pms/models.py, forms.py, serializers.py, services.py, api.py |
| 첨부 크기·형식·파일명 | 구현됨 | pms/file_security.py, models.py; 기존 경계 유지 |
| 분석 CSV 행 검증·원본 보존·출처 ID 중복 | 미구현 | 별도 분석 수집 모델/서비스 추가 (P0) |
| 중대성 미상 | 부분 구현 | AdverseEvent.serious는 bool 기본 False; 기존 값의 의미를 변경하지 않고 분석 데이터에는 UNKNOWN을 명시 (P0) |
| 검색·필터·통계 | 부분 구현 | pms/views.py, api.py; 분석 기간 기준과 비교 통계 추가 (P1) |
| 반복 신호 | 부분 구현 | pms/services.py recurrent_warning; 비교기간·0건 처리·설정값 표시 추가 (P1) |
| 근거 AI | 구현됨 | pms/rule_ai.py, regulation_documents.py, regulatory.py; 검색 chunk ID·원문 인용 검증, 선택형 어댑터·실패 처리. 유료 API 필수화 불필요 |
| 벡터 DB | 적용 불필요 | 기존 근거 문서 검색 사용, 새로운 문서 검색 요구 없음 |
| 검토 저장 | 부분 구현 | WorkTask/TaskHistory, AuditLog; 분석 신호별 인증 사용자·스냅샷 이력 추가 (P2) |
| CSV·분석 보고서 | 부분 구현 | pms/reporting.py 사건 PDF 존재; 분석 CSV와 인쇄/PDF 저장 화면 추가 |
| 테스트·CI | 구현됨 | pms/tests.py, test_workflow.py, test_regulatory*.py, .github/workflows/ci.yml; 자동 발견 테스트로 확장 |

## 구현 경계
기존 업무 데이터를 수정하거나 지우지 않는다. 분석 수집은 독립 테이블에 저장하고 실제/샘플을 분리한다. 원본 파일은 DB binary로 비공개 보존, 정제 행과 오류를 분리 저장. 출처+ID가 있으면 확정 중복 제외, 없으면 기기/제조사/모델/날짜/유형/서술 일치 SHA256을 의심 기준으로 제외하고 오류 목록에 표시한다. 다른 ID의 유사 사건을 자동 병합하지 않는다. CSV는 UTF-8(BOM 허용), 최대 5MB 또는 기존 업로드 제한 중 작은 값, 최대 10000행. 원문은 신뢰하지 않는 데이터로만 표시한다.

동일 길이 직전 기간과 비교하며 날짜 축은 사용자가 선택한 발생일/보고일 하나만 쓴다. 판매량 등 분모가 없어 발생률은 제공하지 않는다. 0건 기준은 증가율 미산출과 신규 보고로 표시한다. 신호는 기기별 보고 건수 증가 규칙이며 인과관계나 제출 적합성을 보장하지 않는다.

스키마는 추가 마이그레이션만 적용. 적용 전 DB/미디어 백업, migrate 후 기존 사건 수 확인. 롤백은 분석 테이블 데이터 손실을 수반하므로 백업 복원 우선. 데모 seed는 실제 DB에 자동 실행하지 않는다.

## 후속 범위
내부 사건 선택 스냅샷과 분석 PDF 서버 버전 보관은 2026-11-01에 추가했다. 대용량 비동기 수집, 운영 개인정보 정책과 기관별 규제 검증은 후속이며 전자서명은 이번 범위에서 제외한다. 기존 AI 어댑터는 운영자가 네트워크 timeout을 구현해야 하며 프로세스 격리 timeout은 pms/ai_boundary.py와 pms/ai_worker.py에 이미 구현되어 있다. 기본 분석은 AI를 호출하지 않는다.

## 구현 완료 및 검증 기록
- `pms/analysis_models.py`와 마이그레이션 0008: 원본 수집/정제 레코드/신호 검토/변경 이력 테이블 추가. 기존 사건·중대성 값은 불변.
- `pms/analysis.py`: CSV 형식·크기·행 수·필수값·날짜·유형 검증, 정제 전 raw/원본 보존, 확정/의심 중복 제외, 미상 보존, 날짜 축별 필터·비교·월별/기기별 건수·중대성 분포, 설정형 규칙, 검토 영속 저장.
- `pms/analysis_views.py`, 분석 템플릿 3개와 `pms/urls.py`, base.html: 한국어 기존 레이아웃·권한·로딩/빈값/오류·근거·저장 이력 접근, CSV 수식 방어, 보고서·PDF 출력. 저장 후 원문·필터·건수가 바뀌면 새 신호이며 이전 이력은 스냅샷 페이지에 보존.
- `pms/analysis_reporting.py`: 기존 ReportLab/한글 TTF 설정으로 실제 서버 PDF 생성. 미설정 시 오류 안내 후 분석 유지. 브라우저 PDF 저장도 제공.
- `pms/rule_ai.py`: 인용 ID/필드/해석의 타입 오류를 검증 예외로 전환, timeout 별도 안내. 실제 외부 API 호출 없음.
- README, .env.example(값 없는 설명), samples/pms-analysis-demo.csv, docs/demo-scenario.md 추가/갱신. 기존 CI의 자동 테스트 발견에 새 테스트가 포함되며 전진 migrate 단계도 추가.

검증: 시작 시 기존 87개 통과(한글 PDF font 미설정 1개 skip). 이후 PDF_KOREAN_FONT=C:\Windows\Fonts\malgun.ttf 설정으로 전체 100개 전부 통과(84.293초, skip 없음). 이후 저장소 샘플 회귀 테스트 추가와 생성 시각 현지화 후 분석 테스트 13개 전부 통과. 서로 다른 테스트 총 101개가 검증됨. AI/스캐너는 mock 사용. 서버 PDF는 pypdf로 구조·한글 텍스트를 확인했으며 자동 시각 렌더링 검사는 하지 않음.

`manage.py check`, `makemigrations --check --dry-run`, compileall, collectstatic 및 runserver 실제 HTTP 로그인 리다이렉트 확인. `check --deploy`는 개발 기본 설정으로 HSTS/SSL redirect/SECRET_KEY/secure session cookie/secure CSRF cookie 경고 5개(실패가 아닌 배포 설정 과제). GitHub 원격 CI와 PostgreSQL은 이 로컬 환경에서 실행하지 않음. 외부 API 실호출/배포/push/commit 없음.

로컬 DB는 별도 작업 폴더에 sqlite backup을 만든 뒤 0008 적용 완료. 기존 PMS 테이블 37개의 행 수 일치, CustomerComplaint 5건 보존. 분석 샘플은 라이브 DB에 넣지 않고 테스트 DB에서 검증함.

갱신된 후속: (1) 명시적 중대성 확인·선택 스냅샷은 구현됨, 기관별 이관 정책 검토는 후속, (2) 영향 입력·내부 사건 선택 페이지네이션은 구현됨, 대용량 비동기 수집은 후속, (3) 이미 구현된 프로세스 격리를 유지한 실제 승인 공급자별 연동 검증, (4) 분석 PDF 보관은 구현됨, 전자서명은 이번 범위 제외, 운영 권한·HTTPS·비밀키 설정 실증은 후속. 규제 규칙 확정과 인과관계 판단은 담당자 검토 범위.
