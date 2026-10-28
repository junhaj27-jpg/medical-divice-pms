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
기존 사건을 분석 코호트로 연결하는 권한 보존 ETL, 대용량 비동기 수집, 분석 PDF의 서버 보관·서명, 운영 개인정보 정책과 기관별 규제 검증은 후속. 기존 AI 어댑터는 운영자가 네트워크 timeout을 구현해야 하며 프로세스 격리 timeout은 후속이다. 기본 분석은 AI를 호출하지 않는다.

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

우선 후속: (1) 기존 사건의 과거 기본 중대성 False를 재확인하는 이관 정책과 권한 보존 ETL, (2) 대용량 수집 비동기 처리·목록 페이지네이션, (3) AI 어댑터 프로세스 격리 timeout 및 실제 승인된 공급자별 연동 검증, (4) 분석 PDF 보관/서명 및 운영 권한·HTTPS·비밀키 설정. 규제 규칙 확정과 인과관계 판단은 담당자 검토 범위.
