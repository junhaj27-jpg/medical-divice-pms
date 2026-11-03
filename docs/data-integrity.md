# 데이터 무결성·이력·운영 이관

## 확인한 현재 구조와 이번 변경

작업 시작 시 `main`은 미커밋 변경 없이 origin/main과 일치했다. 상위 경로 및 저장소에서 적용되는 AGENTS.md는 발견되지 않았다. models.py뿐 아니라 analysis_models.py와 safety_models.py의 등록 모델을 조사했다. 커밋된 7개 소스/템플릿에 충돌 표식이 있었으며 분석·안전 신호와 개정 영향 검토를 모두 살려 해소했다. 단순 한쪽 채택으로 기능을 제거하지 않았다.

동일 번호 0008 두 파일은 0007에서 갈라진 독립 분기다. 0009→0010은 분석 분기, 다른 0008은 영향 검토 분기다. 기존 마이그레이션은 수정하지 않았다. 0011이 두 leaf를 합친다. 0012는 사전 점검·삭제 보호·이력·제약, 0013은 사전 점검·조회 인덱스·추가 도메인 제약을 적용한다. 0014는 nullable 회수 요청 키와 부모 내 고유 제약을 추가하며 기존 행은 NULL을 유지한다. 0015는 마지막 쿼리 대조에서 상태 필터가 없음을 확인하여 신호 인덱스를 실제 scope + 최신 PK 조회에 맞춘다.

기존 물리 스키마의 빈틈은 (1) 제품·UDI·LOT 검증이 일부 폼/serializer에만 있음, (2) 수량·상태 choices가 DB에서 전부 보장되지 않음, (3) 리콜 대상 합계 검사에 공유 잠금이 없음, (4) 위험평가·보고서 현재 행 수정 시 이전 내용 소실, (5) 증빙·행위자 일부 연쇄 삭제/SET_NULL, (6) 승인 해시의 회수·연락 원장 범위 누락이었다. 이번 변경은 이 부분을 보완한다. 모든 역사적 설계 문제를 해결한 것으로 해석하면 안 된다.

[영역별 ERD](erd.md), [실제 필드 데이터 사전](data-dictionary.md)는 `scripts/build_data_model_docs.py`로 Django 등록 메타데이터에서 재생성한다. 도메인 개요·구현/추가/향후 제안과 물리 관계를 구분했다. 현재 사용자 모델 auth.User, PK, 사건번호, upload_to와 기존 파일 경로는 유지한다.

## 보장 범위

| 조건 | DB | 모델/서비스 및 잠금 |
|---|---|---|
| FK 존재·O2O·고유 식별자 | FK/unique/NOT NULL | PROTECT는 Django 삭제 collector 정책, 직접 SQL은 FK 제한 |
| 제품·UDI·LOT 및 환자 사건 일치 | 일반 FK만으로 동등성 보장 불가 | TimeStamped.save에서 관계 검증 명시 호출. 기존 UDI/LOT 제품 연결 변경 차단, 사건과 환자 변경의 역방향 연결 검사 |
| CAPA·리콜·업무·영향 검토 사건 일치 | 각각의 FK 및 업무 두 부모 동시 지정 금지 CHECK | 공통 save, save_task, 영향 검토 처리 서비스 |
| 단일 행 회수량 | 양수 및 상한 CHECK | record_recovery는 양수 int 검사 |
| 대상 LOT 중복·합계 | recall/lot/serial unique | 사건→리콜 순으로 잠근 뒤 합계 확인. 빈 serial은 같은 LOT에서 한 대상이다 |
| 거래처 회수 원장 | recall/lot/partner/unit unique, 회수 예약 상한 CHECK | 사건→recipient 잠금, 조건부 F 업데이트, 원장 추가를 동일 트랜잭션으로 처리. 원장 직접 save 차단 |
| 담당자 활성·역할 | 사용자 FK만 | 모델 저장: 활성 사용자, STAFF는 본인 접수 사건만. 분석·신호 서비스는 활성 RA/QA 또는 ADMIN |
| 현재 대기 승인 | 사건 대상 PENDING+superseded=False 부분 unique | 사건부터 잠그고 최신 요청 검사, 결정 후 재결정 금지 |
| 알림 중복 | nullable dedupe_key unique | 업무·안전 신호·기한 알림은 결정적 key의 get_or_create. null key 수동 알림은 중복 허용 |
| 규칙 적용 | 부모 FK | 전역/계열·사건 잠금과 직전 적용 ID·기한·미리보기 토큰 확인. 의도적 재적용은 새 이력이며 (사건, 규칙) unique를 두지 않는다 |
| 분석 중복 수집 | record.identity unique, batch/row_number unique | 실제/예시 구분 + 출처/원본 ID 또는 정규화 내용 해시. 반복 업로드 시 수집 시도/오류 원본은 남고 분석 레코드는 중복되지 않는다 |
| 실제/예시 자료 연결 | 일부 FK만 | 규칙 적용 서비스, 사건 변경 검사, 신호 조치 검토의 snapshot 제품/LOT/예시 검사. 기존 예시 사건은 자동으로 실제 사건으로 재분류하지 않는다 |
| 증빙 평가 연결 | M2M FK·쌍 unique | 서비스와 m2m pre_add에서 동일 사건 PASSED 파일만 허용 |

일반 save는 full_clean을 자동 실행하지 않는다. 공통 모델 save에서 교차 관계를 직접 검사하며 단일 행의 핵심 불변식은 DB CHECK에 둔다. Form/serializer만 검사하는 구조로 의존하지 않는다. 임의 QuerySet.update, bulk_create, 직접 SQL은 save·이력·여러 행 검증을 우회할 수 있으므로 운영 DB 쓰기 권한은 서비스 외에 개방하지 않는다. PostgreSQL 행 잠금은 SQLite에서 작동하지 않는다. SQLite의 회수 예약은 조건부 UPDATE로 상한을 보호하지만 다중 쓰기 직렬화/재시도 정책까지 PostgreSQL과 동등하다고 주장하지 않는다.

회수 `RecallTarget`(LOT별 계획)과 `RecallRecipient`(거래처별 원장)는 별도 관점이다. 두 합계를 더해서 회수 수량으로 계산하지 않는다. 거래처 단위가 서로 다르면 합산하지 않는다. Recall의 기존 요약 recovered_quantity는 거래처 원장의 합과 자동 동기화되지 않는 레거시 요약이며 화면의 원장 합계는 workflow.recall_totals를 사용한다. 단위 변환·자동 대사는 향후 과제다.

## 상태와 실제 허용 전이

- 사건: RECEIVED → REVIEW → AE_DECISION → RISK → CAPA_DECISION → REPORT_REVIEW → RECALL_REVIEW → APPROVAL → ACTION_COMPLETE → CLOSED. 위험평가·고위험 CAPA·보고 판단·현재 승인 게이트가 추가된다. 마지막 두 전이는 ADMIN. 조치 완료 후 변경 재승인은 사유를 받아 APPROVAL로 되돌리고 버전을 증가시킨다.
- 승인: PENDING → APPROVED 또는 REJECTED만. stale 대기는 decision을 조작하지 않고 superseded=True로 보존한다. 기존 승인·스냅샷은 새 요청으로 대체할 뿐 덮어쓰지 않는다.
- 규칙: DRAFT → REVIEW → APPROVED → EFFECTIVE → RETIRED. REVIEW 반려는 DRAFT, APPROVED도 RETIRED 가능. LEGACY는 자동 승인하지 않고 새 개정 초안을 만든다. 사유·권한·작성자/승인자 분리·미리보기·시행 범위 충돌 검증이 있다.
- CAPA: OPEN/INVESTIGATION/IMPLEMENTATION/EFFECTIVENESS/CLOSED. 기존 구현에 완전한 순차 그래프는 없다. 평가 서비스는 EFFECTIVENESS, 종결은 최신 PASS·평가 내용 일치·업무 완료를 요구한다.
- 업무: WAITING/IN_PROGRESS/REVIEW/DONE. 서비스는 선택값·권한을 검사하며 완전한 순차 그래프는 강제하지 않는다. 변경 전후와 담당자·시각을 TaskHistory로 보존한다.
- 리콜 승인: DRAFT/PENDING/APPROVED/REJECTED, 진행: PLANNED/ACTIVE/COMPLETED/CLOSED. 기존 관리자 처리 화면은 approve/reject/close를 제공하며 일반 API는 승인 변경 및 CLOSED 지정 차단. close는 승인과 종료 보고서를 요구한다. 그 밖의 모든 단계 순차 전이 또는 독립 RecallApproval 테이블은 현재 구현되지 않았다.
- 보고서: DRAFT/REVIEW/APPROVED/SUBMITTED/REJECTED. 별도 제출 서버 통신·접수증·제출 전용 이력 테이블은 없다. 현재 상태를 수정하면 이번 추가 RegulatoryReportHistory가 이전/이후 값을 보존한다. 제출 유효성 전체를 보장하는 상태 머신으로 해석하지 않는다.
- 외부 분석 검토·안전 신호: NEW/REVIEW/ACTION/CLOSED. 선택값·활성 전문 담당자·사유 검사, 안전 신호 ACTION은 기존 CAPA/리콜 연결 필요. 각각 검토 이력을 추가한다. 종료 후 재검토를 막는 순차 그래프는 없다.
- 영향 검토: WAITING/IN_PROGRESS/APPLIED/EXCLUDED. 처리 시 사유·분석 토큰 검사, 완료 상태를 재처리하는 조건은 impact.process_review의 현행 검증을 따른다. 상태 선택지는 DB CHECK, 업무/규칙 적용 연결은 모델에서 추가 검사한다.

## 이력·승인 해시·행위자

새 RiskAssessmentHistory/RegulatoryReportHistory는 실제 저장 트랜잭션에서 의미 있는 필드가 변경될 때 생성한다. 최초 저장은 before={}, 이후는 DB의 저장 전 값을 보존한다. 과거 행에 대한 평가·처리 이력을 이관 시점에 만들어내지 않는다. 기존 행은 새 History가 0개인 것이 정상이며, 첫 실제 수정 시에만 그 시점의 before/after가 기록된다. 역사적 승인/평가 시각을 추정하지 않는다.

HTML 및 API와 관리자 위험평가/보고서 쓰기는 실제 request.user를 _history_actor로 전달한다. 직접 ORM/레거시 명령처럼 행위자 문맥이 없는 저장은 actor=NULL, source=DIRECT_MODEL로 명시한다. 평가 담당자를 실제 수정자로 꾸며 넣지 않는다. 이 경우 실제 행위자 추적은 제한되며 운영 이관은 명령에서 _history_actor와 _history_reason을 명시해야 한다. 새 History의 after에는 대상 PK와 당시 필드 값이 들어가고 자체 PK가 수정 버전 식별자다. 모든 이력이 기존 사건 version을 증가시키지는 않는다.

이력 저장/삭제를 앱 수준에서 차단하고 보호 FK를 사용한다. CAPAEvaluation의 평가 본문은 변경 불가이며 첫 후속 업무 연결만 허용한다. 서비스는 기존 평가를 바꾸지 않고 재평가를 추가한다. 관리자 AuditLog는 읽기 전용이다. DB 관리자 SQL까지 불변을 강제하는 트리거는 추가하지 않았다.

승인 schema=2는 평가/보고 History와 회수·연락 원장을 해시에 포함한다. 기존 schema=1 및 무버전 스냅샷은 재승인 필요로 처리하며 자동 재해시하지 않는다. 상태·읽기 시각 등 승인 본문 밖의 값은 기존 allowlist 원칙을 유지한다. 새 History 행/원장 변경이 있으면 현재 승인을 재검증해야 한다. 환자 본문은 민감정보 최소화 원칙으로 승인 해시 입력에서 제외되어 있으며 환자 변경이 항상 재승인을 요구하는 구조는 아니다. 추가 도메인 필드를 도입하면 approval_integrity.FIELDS 또는 별도 scope의 포함 여부와 schema 증가를 재검토해야 한다.

## 삭제·파일 정책

사건의 익명 환자·이상사례·위험평가·CAPA·첨부, 리콜의 대상, 리콜의 사건 관계를 PROTECT로 바꿨다. 보고서 검토자/승인자, 승인 결정자, 감사 행위자도 PROTECT로 유지한다. 과거 행위자는 사용자 삭제 대신 비활성화로 보존한다. 사용자 프로필·개인 알림·상담 등은 기존 CASCADE를 유지하며 모든 테이블에 soft delete를 도입하지 않았다.

DB 레코드 삭제 보호와 저장소 파일 보존은 별개다. DB에는 기존 상대 경로·SHA-256을 보존하며 증빙 본문을 새 History로 복제하지 않는다. 파일 본문은 Attachment/ReportArtifact/RegulationDocument가 참조한다. Django의 DB 행 삭제가 저장소 파일 자동 삭제를 의미하지 않는다. 파일 보존 기간·백업·외부 저장소 삭제는 별도 운영 정책으로 결정해야 한다. History에는 보고서 체크리스트 등 민감 본문이 포함되므로 기존 접근 통제·백업 범위에서 보호한다.

## 실제 쿼리와 인덱스

| 대상 | 실제 조회 | 결정 |
|---|---|---|
| 사건 | safety.cohort/analyze_safety의 reported_on 범위·제품·LOT, visible_complaints의 reporter 범위 | 기존 complaint_period_product(reported_on,device,lot), complaint_owner_period(reporter,reported_on) 유지. FK 인덱스 중복 생성 안 함 |
| 사건 상태·기한 | complaint_list/status, 기한 알림의 due_date 및 CLOSED 제외 | 현재 규모 측정 없이 추가 복합 인덱스는 보류; 데이터 분포와 실행 계획 확인 필요 |
| 업무 | tasks_for의 담당자 및 상태/기한 | 기존 (assignee,status,due_at) 유지 |
| 승인 | 사건 content_type/object_id 별 최신 created_at,pk 조회 | approval_object_sequence(content_type,object_id,-created_at,-id) 추가. pending 부분 unique와 역할이 다름 |
| 외부 분석 | analysis.analyze의 reported_on 또는 occurred_on 범위 | 각각 날짜 인덱스 추가. identity unique와 batch FK 중복 아님 |
| 안전 신호 | signals_for의 scope 및 safety_views.dashboard의 최신 PK 100개 | signal_scope_sequence(scope,-id) 추가. key unique는 기존 유지. rules.VERSION은 snapshot/key 입력이며 별도 규칙 FK는 없음 |
| 규정/규칙 | jurisdiction/문서번호/edition, family/version/state 필터 | 기존 규정 복합 인덱스, family_key/state 인덱스, family/version unique 유지 |
| 새 이력 | parent별 created_at,pk 조회 | risk_history_parent_time, report_history_parent_time 추가. 부모 FK 단독 인덱스와 시간 범위 정렬 역할 구분 |

성능 수치를 측정하지 않았으며 향상 비율을 주장하지 않는다. 대규모 PostgreSQL의 DDL 잠금·인덱스 생성 시간은 별도 점검 필요하다.

## 안전한 이관 절차

1. 운영 DB를 백업하고 복구 검증한 뒤 별도 복사본/스테이징 DB에서 실행한다. 이 작업은 실제 사용자 DB에 migrate하지 않았다.
2. `python manage.py audit_data_integrity --database default`로 읽기 전용 점검한다. JSON의 model, pk, rule로 위반을 식별하며 원문 민감정보는 출력하지 않는다. 모델/열이 아직 없는 매우 오래된 스키마는 우선 복사본에서 0011까지 적용한 뒤 명령을 실행한다.
3. 0012/0013은 동일한 동결 점검을 RunPython으로 제약 적용 전에 실행한다. 위반이 있으면 RuntimeError로 중단하며 행 삭제·병합·수량 보정·자동 예시 재분류를 수행하지 않는다. 점검 결과가 없다고 모든 가능한 외부 SQL 손상을 탐지한다는 뜻은 아니다.
4. 오류별로 해당 사건/LOT/UDI 또는 원장/분석 원본을 담당자가 대조하고, 정정 근거·행위자·검토 시각·원본 출처를 남겨 명시적 서비스/검토된 이관 명령으로 수정한다. 중복 원장은 단순 삭제·합산하지 말고 실제 중복인지 검토하고 보존 정책에 따라 별도 이관 계획을 세운다. 과거 평가 이력을 생성해 오류를 숨기지 않는다.
5. 점검을 재실행한 뒤 0012/0013 전진 적용과 회귀 테스트를 수행한다. SQLite/PostgreSQL의 일반적인 migration atomic 범위는 마이그레이션 단위다. 0013 실패 시 이미 성공한 0012까지 자동 롤백된다고 가정하지 않는다.
6. 이관 기록은 별도 운영 기록에 source DB/백업 식별자, 실제 이관 시각, 실행자, 적용 migration 목록, 사전 점검 결과와 승인된 정정 목록을 보관한다. 기존 스냅샷·파일 경로는 그대로 남긴다.

## 남은 제한

Approval와 AuditLog의 기존 문자열 대상은 실제 FK가 아니다. SafetySignal.snapshot.evidence, SafetyReview.links와 AnalysisReview.snapshot도 JSON 논리 참조다. 삭제 시 DB 보호·제품 일치를 모든 JSON 경로에서 강제할 수 없다. 별도 명시 연결 테이블 도입은 향후 제안이며 ERD에 구현된 관계로 그리지 않았다. 새 GenericForeignKey는 도입하지 않았다.

회수 HTML 폼은 UUID request_key를 발급한다. 서비스는 (recipient,request_key) 고유 제약과 부모 잠금으로 같은 요청의 재전송을 기존 원장으로 반환하며 내용이 바뀐 키 재사용은 차단한다. 기존 명령/호출 호환을 위해 키 없는 호출도 허용하므로 이 경우 호출자가 중복 전송을 관리해야 한다. 서로 다른 키의 두 요청이 실제로 같은 물품인지까지 판별하지는 못한다. 과거 원장에는 임의 요청 키를 채워 넣지 않는다.

담당자 검증은 배정 시점 기준이며 사용자 비활성화·역할 변경을 모든 배정 행과 같은 트랜잭션으로 잠그지는 않는다. 비활성 담당 업무는 재배정해야 하며 과거 행위자 FK는 보존한다. 서비스 외 직접 SQL·bulk 쓰기, 전 DB에 대한 삭제 금지, 완전한 제출 상태 머신, 문서 파일 외부 삭제, PostgreSQL 실측 동시성/운영 부하는 별도 보완 사항이다.

## 실제 검증 결과 — 2026-11-03 (Asia/Seoul)

Windows의 번들 Python과 저장소 .deps의 Django 5.2.18을 사용했다. PATH에 python 명령이 없어 실제 실행은 번들 python.exe로 수행했으며 아래 명령의 인수는 동일하다. SQLITE_PATH를 work/erd-validation의 격리 경로로 지정했다. 최종 전체 테스트에는 PDF_KOREAN_FONT=C:\Windows\Fonts\malgun.ttf를 설정했다.

| 검증 | 실제 결과 |
|---|---|
| python manage.py check | exit 0, 문제 없음 |
| python manage.py makemigrations --check --dry-run | exit 0, No changes detected |
| python manage.py showmigrations --plan | exit 0, 0011~0015 의존성 계획 확인 |
| python manage.py migrate --noinput | 새 빈 DB에 0015까지 전체 설치 성공; 격리 DB 재실행도 적용할 항목 없음 |
| python manage.py audit_data_integrity | 격리 DB 위반 0건 |
| python manage.py test --noinput | 168개 실행, 161개 통과, PostgreSQL 전용 7개 skip, 실패 0; 185.174초 |
| git diff --check | exit 0. Git의 LF→CRLF 안내는 검증 실패가 아님 |
| 물리 문서 재생성 | 46개 PMS 모델, 8개 Mermaid 블록, auth/M2M 테이블 포함. 블록/테이블 괄호 검사 성공 |

초기 폰트 미설정 실행은 168개 중 159개 통과·9개 skip이었고, 이후 한글 폰트 설정 실행에서 PDF 2개까지 통과했다. PostgreSQL 행 잠금·동시 승인/회수/대상·분석 중복 수집 7개는 SQLite 결과로 통과 처리하지 않았다. 기존 SQLite 회수 경합 테스트는 별도로 실행됐으며 PostgreSQL 검증과 구분한다.

원본 db.sqlite3는 작업 당시 0바이트였다. 읽기 전용 SQLite backup 복사본의 설치 성공은 확인했으나 이를 실제 업무 데이터 이관 검증이라고 주장하지 않는다. 데이터가 있는 기존 스키마 전진 적용은 MigrationExecutor 회귀 테스트로 검증했다. 위험평가 위반 행이 있으면 마이그레이션이 중단되고 원본 행을 보존하며, 명시적 fixture 정정 후 전진 적용이 가능하고 과거 History를 합성하지 않음을 확인했다. 기존 규칙·사건 기한·승인 스냅샷·첨부 경로 보존 테스트도 통과했다.

미검증: 실제 PostgreSQL 실행·운영 데이터 복사본·운영 부하/쿼리 실행 계획·DDL 잠금 시간·Mermaid 렌더러의 그래픽 출력. 자동 배포, git commit, git push, 실제 사용자 DB migrate는 수행하지 않았다. 전체 테스트 로그와 명령별 로그는 무시된 work/erd-validation 디렉터리에 보관했다.

최종 인덱스 조정 뒤 최신 스키마에서 데이터 모델·안전 신호 대상 테스트 23개도 추가 실행하여 모두 통과했다(7.096초).

