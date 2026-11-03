# 데이터 사전

scripts/build_data_model_docs.py로 실제 등록 모델 메타데이터에서 재생성한다. DB 필수는 NOT NULL 기준이며 blank=True(폼 선택)와 구분한다. 빈 문자열 허용은 NOT NULL과 별개다. 기본값은 Django 기본값이며 별도 DB default가 없다. BigAutoField는 기존 PK를 유지한다. FK/OneToOne은 기본 인덱스, unique는 고유 인덱스를 수반한다. PostgreSQL/SQLite의 SQL 타입은 다를 수 있다.

개인정보 기준: 사용자 계정·이메일·IP는 개인정보, 익명 환자·사건 본문·증빙·분석 원문·스냅샷은 재식별 가능 민감 자료로 취급한다. FK actor/assignee/reporter 등도 계정 추적 정보다. 인증 password는 해시다. 원문 파일은 DB 경로와 저장소 객체를 별도 보존한다.

DB 보장과 서비스 검증은 각 모델에서 구분한다. QuerySet.update/bulk_create/raw SQL은 모델 save·clean·이력 생성을 우회한다. 운영 쓰기는 문서화한 서비스/폼/API만 허용한다. 일반 Django save가 full_clean을 호출한다고 가정하지 않으며 공통 save는 관계 검증을 명시 호출한다.

## Profile — `pms_profile`

사용자 역할·시간대.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| user (user_id) | OneToOneField / integer | 예 / False | 없음 | auth_user.id / CASCADE |
| role (role) | CharField(10) / varchar(10) | 예 / False | Profile.Role.STAFF | — |
| timezone_name (timezone_name) | CharField(64) / varchar(64) | 예 / False | 'Asia/Seoul' | — |

DB 제약:

- PK/필드 unique: id, user
- unique_together: []

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.
- `role` 허용값: STAFF, RA_QA, ADMIN

## Manufacturer — `pms_manufacturer`

제조사.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| name (name) | CharField(200) / varchar(200) | 예 / False | 없음 | — |
| country (country) | CharField(100) / varchar(100) | 예 / True | 없음 | — |
| contact_email (contact_email) | CharField(254) / varchar(254) | 예 / True | 없음 | — |

DB 제약:

- PK/필드 unique: id, name
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## MedicalDevice — `pms_medicaldevice`

제품.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| manufacturer (manufacturer_id) | ForeignKey / bigint | 예 / False | 없음 | pms_manufacturer.id / PROTECT |
| name (name) | CharField(200) / varchar(200) | 예 / False | 없음 | — |
| model_number (model_number) | CharField(100) / varchar(100) | 예 / False | 없음 | — |
| risk_class (risk_class) | CharField(20) / varchar(20) | 예 / True | 없음 | — |
| active (active) | BooleanField / bool | 예 / False | True | — |

DB 제약:

- PK/필드 unique: id
- unique_together: (('manufacturer', 'model_number'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## UDI — `pms_udi`

UDI 식별자.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| device (device_id) | ForeignKey / bigint | 예 / False | 없음 | pms_medicaldevice.id / CASCADE |
| device_identifier (device_identifier) | CharField(100) / varchar(100) | 예 / False | 없음 | — |

DB 제약:

- PK/필드 unique: id, device_identifier
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 모델 저장: 기존 제품 재연결 금지.

## ProductLot — `pms_productlot`

생산 LOT·일련번호.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| device (device_id) | ForeignKey / bigint | 예 / False | 없음 | pms_medicaldevice.id / CASCADE |
| udi (udi_id) | ForeignKey / bigint | 예 / False | 없음 | pms_udi.id / PROTECT |
| lot_number (lot_number) | CharField(100) / varchar(100) | 예 / False | 없음 | — |
| serial_number (serial_number) | CharField(100) / varchar(100) | 예 / True | 없음 | — |
| manufactured_on (manufactured_on) | DateField / date | 아니오 / True | 없음 | — |
| expires_on (expires_on) | DateField / date | 아니오 / True | 없음 | — |
| distributed_quantity (distributed_quantity) | PositiveIntegerField / integer unsigned | 예 / False | 0 | — |

DB 제약:

- PK/필드 unique: id
- unique_together: (('udi', 'lot_number', 'serial_number'),)
- 타입의 암묵적 DB 비음수 CHECK: distributed_quantity

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 모델 저장: UDI 제품 일치, 기존 항목 제품·UDI 재연결 금지.

## CustomerComplaint — `pms_customercomplaint`

PMS 사건.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| device (device_id) | ForeignKey / bigint | 예 / False | 없음 | pms_medicaldevice.id / PROTECT |
| udi (udi_id) | ForeignKey / bigint | 예 / False | 없음 | pms_udi.id / PROTECT |
| lot (lot_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_productlot.id / PROTECT |
| serial_number (serial_number) | CharField(100) / varchar(100) | 예 / True | 없음 | — |
| complaint_type (complaint_type) | CharField(50) / varchar(50) | 예 / False | 없음 | — |
| title (title) | CharField(200) / varchar(200) | 예 / False | 없음 | — |
| description (description) | TextField / text | 예 / False | 없음 | — |
| occurred_on (occurred_on) | DateField / date | 예 / False | 없음 | — |
| reported_on (reported_on) | DateField / date | 예 / False | localdate | — |
| reporter (reporter_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| assignee (assignee_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / SET_NULL |
| status (status) | CharField(20) / varchar(20) | 예 / False | CustomerComplaint.Status.RECEIVED | — |
| due_date (due_date) | DateField / date | 아니오 / True | 없음 | — |
| version (version) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: version
- <CheckConstraint: condition=(AND: ('status__in', ['RECEIVED', 'REVIEW', 'AE_DECISION', 'RISK', 'CAPA_DECISION', 'REPORT_REVIEW', 'RECALL_REVIEW', 'APPROVAL', 'ACTION_COMPLETE', 'CLOSED'])) name='customercomplaint_status_valid'>

명시 인덱스: complaint_period_product: ['reported_on', 'device', 'lot']; complaint_owner_period: ['reporter', 'reported_on']

앱/서비스 조건: model_integrity: 제품·UDI·LOT, 활성/역할 배정, 기존 리콜·규칙의 역방향 일치. services.TRANSITIONS: 상태 전이·승인 게이트.
- `status` 허용값: RECEIVED, REVIEW, AE_DECISION, RISK, CAPA_DECISION, REPORT_REVIEW, RECALL_REVIEW, APPROVAL, ACTION_COMPLETE, CLOSED

## PatientAnonymousInfo — `pms_patientanonymousinfo`

사건별 익명 환자 정보.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| complaint (complaint_id) | OneToOneField / bigint | 예 / False | 없음 | pms_customercomplaint.id / PROTECT |
| anonymous_code (anonymous_code) | CharField(64) / varchar(64) | 예 / False | 없음 | — |
| age_band (age_band) | CharField(20) / varchar(20) | 예 / True | 없음 | — |
| sex (sex) | CharField(20) / varchar(20) | 예 / True | 없음 | — |
| notes (notes) | TextField / text | 예 / True | 없음 | — |

DB 제약:

- PK/필드 unique: id, complaint, anonymous_code
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: clean의 식별정보 키워드 검사는 완전한 개인정보 탐지가 아니다. 연결 이상사례 사건 일치.

## AdverseEvent — `pms_adverseevent`

사건별 이상사례 판단.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| complaint (complaint_id) | OneToOneField / bigint | 예 / False | 없음 | pms_customercomplaint.id / PROTECT |
| patient (patient_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_patientanonymousinfo.id / PROTECT |
| event_type (event_type) | CharField(50) / varchar(50) | 예 / False | 없음 | — |
| outcome (outcome) | CharField(100) / varchar(100) | 예 / False | 없음 | — |
| serious (serious) | BooleanField / bool | 예 / False | False | — |
| narrative (narrative) | TextField / text | 예 / False | 없음 | — |

DB 제약:

- PK/필드 unique: id, complaint
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 모델 저장 및 serializer: patient.complaint_id == complaint_id.

## RiskAssessment — `pms_riskassessment`

현재 위험평가.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| complaint (complaint_id) | OneToOneField / bigint | 예 / False | 없음 | pms_customercomplaint.id / PROTECT |
| severity (severity) | PositiveSmallIntegerField / smallint unsigned | 예 / False | 없음 | — |
| probability (probability) | PositiveSmallIntegerField / smallint unsigned | 예 / False | 없음 | — |
| score (score) | PositiveSmallIntegerField / smallint unsigned | 예 / False | 1 | — |
| level (level) | CharField(10) / varchar(10) | 예 / False | 없음 | — |
| capa_review_required (capa_review_required) | BooleanField / bool | 예 / False | False | — |
| rationale (rationale) | TextField / text | 예 / True | 없음 | — |
| assessed_by (assessed_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |

DB 제약:

- PK/필드 unique: id, complaint
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: severity, probability, score
- <CheckConstraint: condition=(AND: ('probability__range', (1, 5)), ('severity__range', (1, 5))) name='risk_values_range'>
- <CheckConstraint: condition=(AND: ('score', <CombinedExpression: F(severity) * F(probability)>)) name='risk_score_product'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## CAPA — `pms_capa`

시정·예방 조치.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| complaint (complaint_id) | ForeignKey / bigint | 예 / False | 없음 | pms_customercomplaint.id / PROTECT |
| title (title) | CharField(200) / varchar(200) | 예 / False | 없음 | — |
| root_cause (root_cause) | TextField / text | 예 / True | 없음 | — |
| corrective_action (corrective_action) | TextField / text | 예 / False | 없음 | — |
| preventive_action (preventive_action) | TextField / text | 예 / True | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| due_date (due_date) | DateField / date | 예 / False | 없음 | — |
| status (status) | CharField(20) / varchar(20) | 예 / False | CAPA.Status.OPEN | — |
| action_result (action_result) | TextField / text | 예 / True | 없음 | — |
| evaluation_criteria (evaluation_criteria) | TextField / text | 예 / True | 없음 | — |
| evaluation_due (evaluation_due) | DateField / date | 아니오 / True | 없음 | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- <CheckConstraint: condition=(AND: ('status__in', ['OPEN', 'INVESTIGATION', 'IMPLEMENTATION', 'EFFECTIVENESS', 'CLOSED'])) name='capa_status_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 종결 시 최신 PASS 평가와 결과·기준·예정일 일치; close_capa에서 연결 업무 완료.
- `status` 허용값: OPEN, INVESTIGATION, IMPLEMENTATION, EFFECTIVENESS, CLOSED

## Recall — `pms_recall`

회수 계획·상태.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| complaint (complaint_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_customercomplaint.id / PROTECT |
| title (title) | CharField(200) / varchar(200) | 예 / False | 없음 | — |
| reason (reason) | TextField / text | 예 / False | 없음 | — |
| risk_level (risk_level) | CharField(10) / varchar(10) | 예 / False | 없음 | — |
| device (device_id) | ForeignKey / bigint | 예 / False | 없음 | pms_medicaldevice.id / PROTECT |
| distributed_quantity (distributed_quantity) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| target_quantity (target_quantity) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| recovered_quantity (recovered_quantity) | PositiveIntegerField / integer unsigned | 예 / False | 0 | — |
| start_date (start_date) | DateField / date | 예 / False | 없음 | — |
| expected_end_date (expected_end_date) | DateField / date | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| approval_status (approval_status) | CharField(10) / varchar(10) | 예 / False | Recall.Approval.DRAFT | — |
| decision_reason (decision_reason) | TextField / text | 예 / True | 없음 | — |
| progress_status (progress_status) | CharField(10) / varchar(10) | 예 / False | Recall.Progress.PLANNED | — |
| closure_report (closure_report) | TextField / text | 예 / True | 없음 | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: distributed_quantity, target_quantity, recovered_quantity
- <CheckConstraint: condition=(AND: ('recovered_quantity__lte', F(target_quantity)), ('target_quantity__lte', F(distributed_quantity))) name='recall_quantity_bounds'>
- <CheckConstraint: condition=(AND: ('approval_status__in', ['DRAFT', 'PENDING', 'APPROVED', 'REJECTED'])) name='recall_approval_status_valid'>
- <CheckConstraint: condition=(AND: ('progress_status__in', ['PLANNED', 'ACTIVE', 'COMPLETED', 'CLOSED'])) name='recall_progress_status_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 모델 저장: 사건 제품 일치, 기존 대상과 제품 일치·목표 축소 검사.
- `approval_status` 허용값: DRAFT, PENDING, APPROVED, REJECTED
- `progress_status` 허용값: PLANNED, ACTIVE, COMPLETED, CLOSED

## RecallTarget — `pms_recalltarget`

회수 대상 LOT.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| recall (recall_id) | ForeignKey / bigint | 예 / False | 없음 | pms_recall.id / PROTECT |
| lot (lot_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productlot.id / PROTECT |
| serial_number (serial_number) | CharField(100) / varchar(100) | 예 / True | 없음 | — |
| target_quantity (target_quantity) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: target_quantity
- <UniqueConstraint: fields=('recall', 'lot', 'serial_number') name='unique_recall_target'>
- <CheckConstraint: condition=(AND: ('target_quantity__gte', 1)) name='positive_recall_target'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 사건→리콜 잠금 후 LOT 제품 일치와 대상 수량 합계 검사.

## RegulatoryReport — `pms_regulatoryreport`

규제보고 판단·제출 상태.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| complaint (complaint_id) | ForeignKey / bigint | 예 / False | 없음 | pms_customercomplaint.id / PROTECT |
| document_number (document_number) | CharField(50) / varchar(50) | 예 / False | 없음 | — |
| required (required) | BooleanField / bool | 예 / False | False | — |
| checklist (checklist) | JSONField / text | 예 / True | dict | — |
| investigation_result (investigation_result) | TextField / text | 예 / True | 없음 | — |
| status (status) | CharField(12) / varchar(12) | 예 / False | RegulatoryReport.Status.DRAFT | — |
| author (author_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |

DB 제약:

- PK/필드 unique: id, document_number
- unique_together: ()
- <CheckConstraint: condition=(AND: ('status__in', ['DRAFT', 'REVIEW', 'APPROVED', 'SUBMITTED', 'REJECTED'])) name='regulatoryreport_status_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.
- `status` 허용값: DRAFT, REVIEW, APPROVED, SUBMITTED, REJECTED

## Attachment — `pms_attachment`

검사된 증빙 파일 참조.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| ra_profile (ra_profile_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_regulatoryprofile.id / PROTECT |
| complaint (complaint_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_customercomplaint.id / PROTECT |
| file (file) | FileField(100) / varchar(100) | 예 / False | 없음 | — |
| original_name (original_name) | CharField(255) / varchar(255) | 예 / True | 없음 | — |
| uploaded_by (uploaded_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| scan_status (scan_status) | CharField(12) / varchar(12) | 예 / False | 'PENDING' | — |
| sha256 (sha256) | CharField(64) / varchar(64) | 예 / True | 없음 | — |
| detected_type (detected_type) | CharField(20) / varchar(20) | 예 / True | 없음 | — |
| scanned_at (scanned_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- <CheckConstraint: condition=(OR: (AND: ('complaint__isnull', False), ('ra_profile__isnull', True)), (AND: ('complaint__isnull', True), ('ra_profile__isnull', False))) name='attachment_one_context'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 사건 또는 RA 프로필 하나만 지정. RA 증빙은 범위·파일 덮어쓰기 금지. 기존 검사·파일 해시·비공개 다운로드 재사용.
- `scan_status` 허용값: PENDING, PASSED, QUARANTINED, FAILED

## Approval — `pms_approval`

승인 요청·결정·무결성 스냅샷.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| superseded (superseded) | BooleanField / bool | 예 / False | False | — |
| content_type (content_type) | CharField(50) / varchar(50) | 예 / False | 없음 | — |
| object_id (object_id) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| requested_by (requested_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| decided_by (decided_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| decision (decision) | CharField(10) / varchar(10) | 예 / False | Approval.Decision.PENDING | — |
| reason (reason) | TextField / text | 예 / True | 없음 | — |
| snapshot (snapshot) | JSONField / text | 예 / True | dict | — |
| decided_at (decided_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: object_id
- <CheckConstraint: condition=(AND: ('decision__in', ['PENDING', 'APPROVED', 'REJECTED'])) name='approval_decision_valid'>
- <UniqueConstraint: fields=('content_type', 'object_id') name='unique_pending_case_approval' condition=(AND: ('content_type', 'CustomerComplaint'), ('decision', 'PENDING'), ('superseded', False))>

명시 인덱스: approval_object_sequence: ['content_type', 'object_id', '-created_at', '-id']

앱/서비스 조건: services: 사건 잠금, 현재 대기 중복 차단, 처리 완료 불변, 해시 버전 2 재검증. content_type/object_id는 논리 참조로 DB FK가 아니다.
- `decision` 허용값: PENDING, APPROVED, REJECTED

## AuditLog — `pms_auditlog`

행위 감사.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| actor (actor_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| action (action) | CharField(30) / varchar(30) | 예 / False | 없음 | — |
| object_type (object_type) | CharField(80) / varchar(80) | 예 / True | 없음 | — |
| object_id (object_id) | CharField(80) / varchar(80) | 예 / True | 없음 | — |
| before (before) | JSONField / text | 예 / True | dict | — |
| after (after) | JSONField / text | 예 / True | dict | — |
| ip_address (ip_address) | GenericIPAddressField(39) / char(39) | 아니오 / True | 없음 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## Notification — `pms_notification`

사용자 알림.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| user (user_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / CASCADE |
| title (title) | CharField(200) / varchar(200) | 예 / False | 없음 | — |
| message (message) | TextField / text | 예 / False | 없음 | — |
| level (level) | CharField(10) / varchar(10) | 예 / False | 'INFO' | — |
| due_at (due_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| read_at (read_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| dedupe_key (dedupe_key) | CharField(200) / varchar(200) | 아니오 / True | 없음 | — |

DB 제약:

- PK/필드 unique: id, dedupe_key
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## AssistantConversation — `pms_assistantconversation`

RA 상담 세션.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| user (user_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / CASCADE |
| title (title) | CharField(120) / varchar(120) | 예 / False | 'RA 업무 상담' | — |
| is_active (is_active) | BooleanField / bool | 예 / False | True | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## AssistantMessage — `pms_assistantmessage`

상담 내용.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| conversation (conversation_id) | ForeignKey / bigint | 예 / False | 없음 | pms_assistantconversation.id / CASCADE |
| role (role) | CharField(10) / varchar(10) | 예 / False | 없음 | — |
| content (content) | TextField(4000) / text | 예 / False | 없음 | — |
| intent (intent) | CharField(40) / varchar(40) | 예 / True | 없음 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.
- `role` 허용값: USER, ASSISTANT

## WorkTask — `pms_worktask`

사건 담당 업무.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| ra_profile (ra_profile_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_regulatoryprofile.id / PROTECT |
| complaint (complaint_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_customercomplaint.id / PROTECT |
| capa (capa_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_capa.id / PROTECT |
| recall (recall_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_recall.id / PROTECT |
| assignee (assignee_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| title (title) | CharField(200) / varchar(200) | 예 / False | 없음 | — |
| description (description) | TextField / text | 예 / True | 없음 | — |
| priority (priority) | CharField(10) / varchar(10) | 예 / False | 'NORMAL' | — |
| due_at (due_at) | DateTimeField / datetime | 예 / False | 없음 | — |
| status (status) | CharField(16) / varchar(16) | 예 / False | WorkTask.Status.WAITING | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- <CheckConstraint: condition=(OR: (AND: ('complaint__isnull', False), ('ra_profile__isnull', True)), (AND: ('complaint__isnull', True), ('ra_profile__isnull', False))) name='worktask_one_context'>
- <CheckConstraint: condition=(OR: ('capa__isnull', True), ('recall__isnull', True)) name='task_one_action_parent'>
- <CheckConstraint: condition=(AND: ('status__in', ['WAITING', 'IN_PROGRESS', 'REVIEW', 'DONE'])) name='worktask_status_valid'>

명시 인덱스: pms_worktas_assigne_e0e5e2_idx: ['assignee', 'status', 'due_at']

앱/서비스 조건: 사건 또는 RA 프로필 중 정확히 하나. 사건/조치 일치, 활성 담당자, STAFF 사건 접수자 또는 본인 배정 RA 업무만. RA 범위 재이동 금지. save_task에서 권한·시각·이력.
- `priority` 허용값: LOW, NORMAL, HIGH, URGENT
- `status` 허용값: WAITING, IN_PROGRESS, REVIEW, DONE

## TaskHistory — `pms_taskhistory`

업무 변경 이력.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| task (task_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / PROTECT |
| actor (actor_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| before (before) | JSONField / text | 예 / False | dict | — |
| after (after) | JSONField / text | 예 / False | dict | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## CAPAEvaluation — `pms_capaevaluation`

CAPA 효과성 평가·증빙.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| capa (capa_id) | ForeignKey / bigint | 예 / False | 없음 | pms_capa.id / PROTECT |
| action_result (action_result) | TextField / text | 예 / False | 없음 | — |
| criteria (criteria) | TextField / text | 예 / False | 없음 | — |
| scheduled_on (scheduled_on) | DateField / date | 예 / False | 없음 | — |
| evaluator (evaluator_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| evaluated_on (evaluated_on) | DateField / date | 예 / False | 없음 | — |
| verdict (verdict) | CharField(10) / varchar(10) | 예 / False | 없음 | — |
| rationale (rationale) | TextField / text | 예 / False | 없음 | — |
| followup (followup_id) | OneToOneField / bigint | 아니오 / True | 없음 | pms_worktask.id / PROTECT |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_capaevaluation_evidence`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id, followup
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 평가 서비스는 미래일 차단, 동일 사건 PASSED 증빙만 연결. m2m pre_add도 동일 조건 검사. 본문 수정 금지, 최초 후속 업무 연결 허용.
- `verdict` 허용값: PASS, FAIL

## BusinessPartner — `pms_businesspartner`

거래처.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| name (name) | CharField(200) / varchar(200) | 예 / False | 없음 | — |

DB 제약:

- PK/필드 unique: id, name
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## RecallRecipient — `pms_recallrecipient`

거래처·LOT·단위별 회수 대상.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| recall (recall_id) | ForeignKey / bigint | 예 / False | 없음 | pms_recall.id / PROTECT |
| lot (lot_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productlot.id / PROTECT |
| partner (partner_id) | ForeignKey / bigint | 예 / False | 없음 | pms_businesspartner.id / PROTECT |
| unit (unit) | CharField(20) / varchar(20) | 예 / False | '개' | — |
| target_quantity (target_quantity) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| recovered_total (recovered_total) | PositiveIntegerField / integer unsigned | 예 / False | 0 | — |
| notified_on (notified_on) | DateField / date | 아니오 / True | 없음 | — |
| notification_method (notification_method) | CharField(100) / varchar(100) | 예 / True | 없음 | — |
| replied_on (replied_on) | DateField / date | 아니오 / True | 없음 | — |
| reply_status (reply_status) | CharField(12) / varchar(12) | 예 / False | 'WAITING' | — |
| unrecovered_reason (unrecovered_reason) | TextField / text | 예 / True | 없음 | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: target_quantity, recovered_total
- <UniqueConstraint: fields=('recall', 'lot', 'partner', 'unit') name='unique_recall_recipient'>
- <CheckConstraint: condition=(AND: ('recovered_total__lte', F(target_quantity))) name='recipient_recovery_limit'>
- <CheckConstraint: condition=(AND: ('target_quantity__gte', 1)) name='positive_recipient_target'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 모델 저장: LOT 제품 일치, 원장 키·목표·누적 값 직접 변경 금지. 서비스: 회수 예약과 원장 동시 저장.
- `reply_status` 허용값: WAITING, REPLIED, DECLINED

## RecoveryEntry — `pms_recoveryentry`

추가 회수 원장.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| request_key (request_key) | CharField(64) / varchar(64) | 아니오 / True | 없음 | — |
| recipient (recipient_id) | ForeignKey / bigint | 예 / False | 없음 | pms_recallrecipient.id / PROTECT |
| recovered_on (recovered_on) | DateField / date | 예 / False | 없음 | — |
| quantity (quantity) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| actor (actor_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: quantity
- <UniqueConstraint: fields=('recipient', 'request_key') name='unique_recovery_request'>
- <CheckConstraint: condition=(AND: ('quantity__gte', 1)) name='positive_recovery_quantity'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: record_recovery만 추가 허용. 부모 잠금+조건부 F 업데이트+원장 insert를 한 트랜잭션으로 실행.

## RecallContact — `pms_recallcontact`

회수 연락 이력.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| recipient (recipient_id) | ForeignKey / bigint | 예 / False | 없음 | pms_recallrecipient.id / PROTECT |
| contacted_at (contacted_at) | DateTimeField / datetime | 예 / False | 없음 | — |
| method (method) | CharField(100) / varchar(100) | 예 / False | 없음 | — |
| note (note) | TextField / text | 예 / False | 없음 | — |
| actor (actor_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ReportingRule — `pms_reportingrule`

규칙 버전.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| name (name) | CharField(200) / varchar(200) | 예 / False | 없음 | — |
| version (version) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| conditions (conditions) | JSONField / text | 예 / True | dict | — |
| basis (basis) | CharField(20) / varchar(20) | 예 / True | '' | — |
| days (days) | PositiveIntegerField / integer unsigned | 아니오 / True | 없음 | — |
| day_type (day_type) | CharField(12) / varchar(12) | 예 / True | '' | — |
| holidays (holidays) | JSONField / text | 예 / True | list | — |
| effective_on (effective_on) | DateField / date | 아니오 / True | 없음 | — |
| change_reason (change_reason) | TextField / text | 예 / False | 없음 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | True | — |
| family_key (family_key) | UUIDField(32) / char(32) | 예 / False | uuid4 | — |
| supersedes (supersedes_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_reportingrule.id / PROTECT |
| state (state) | CharField(12) / varchar(12) | 예 / False | ReportingRule.State.DRAFT | — |
| created_by (created_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| activated_at (activated_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| jurisdiction (jurisdiction) | CharField(120) / varchar(120) | 예 / True | 없음 | — |
| device (device_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_medicaldevice.id / PROTECT |
| scope_description (scope_description) | TextField / text | 예 / True | 없음 | — |
| reporting_authority (reporting_authority) | CharField(200) / varchar(200) | 예 / True | 없음 | — |
| obligation_trigger (obligation_trigger) | TextField / text | 예 / True | 없음 | — |
| deadline_expression (deadline_expression) | TextField / text | 예 / True | 없음 | — |
| deadline_unit (deadline_unit) | CharField(8) / varchar(8) | 예 / True | 없음 | — |
| include_start (include_start) | BooleanField / bool | 아니오 / True | 없음 | — |
| deadline_time (deadline_time) | TimeField / time | 아니오 / True | 없음 | — |
| timezone_name (timezone_name) | CharField(64) / varchar(64) | 예 / True | 없음 | — |
| exceptions (exceptions) | TextField / text | 예 / True | 없음 | — |
| effective_until (effective_until) | DateField / date | 아니오 / True | 없음 | — |
| holiday_verified_from (holiday_verified_from) | DateField / date | 아니오 / True | 없음 | — |
| holiday_verified_until (holiday_verified_until) | DateField / date | 아니오 / True | 없음 | — |
| holiday_checked_on (holiday_checked_on) | DateField / date | 아니오 / True | 없음 | — |
| unresolved_items (unresolved_items) | JSONField / text | 예 / True | list | — |
| source_expressions (source_expressions) | JSONField / text | 예 / True | dict | — |
| origin (origin) | CharField(12) / varchar(12) | 예 / False | 'MANUAL' | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: version, days, revision
- <UniqueConstraint: fields=('name', 'version') name='unique_reporting_rule_version'>
- <UniqueConstraint: fields=('family_key', 'version') name='unique_rule_family_version'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: regulatory: 역할·분리 승인·원문 인용·시행일·범위 충돌·낙관적 토큰 및 계열 잠금. 직접 save는 제한.
- `basis` 허용값: REPORTED, OCCURRED, AWARE, CUSTOM
- `day_type` 허용값: CALENDAR, BUSINESS
- `state` 허용값: LEGACY, DRAFT, REVIEW, APPROVED, EFFECTIVE, RETIRED
- `deadline_unit` 허용값: DAYS, HOURS
- `origin` 허용값: MANUAL, EVIDENCE, AI

## RuleApplication — `pms_ruleapplication`

사건 규칙 적용 스냅샷.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| previous_snapshot (previous_snapshot) | JSONField / text | 예 / True | dict | — |
| complaint (complaint_id) | ForeignKey / bigint | 예 / False | 없음 | pms_customercomplaint.id / PROTECT |
| rule (rule_id) | ForeignKey / bigint | 예 / False | 없음 | pms_reportingrule.id / PROTECT |
| snapshot (snapshot) | JSONField / text | 예 / False | 없음 | — |
| due_at (due_at) | DateTimeField / datetime | 예 / False | 없음 | — |
| actor (actor_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reason (reason) | TextField / text | 예 / False | 없음 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 서비스는 시행 규칙·사건 조건·예시 분리·미리보기·직전 적용 토큰 검사. 재적용은 새 이력이다.

## ReportArtifact — `pms_reportartifact`

버전별 보고 PDF·묶음 해시.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| complaint (complaint_id) | ForeignKey / bigint | 예 / False | 없음 | pms_customercomplaint.id / PROTECT |
| number (number) | CharField(80) / varchar(80) | 예 / False | 없음 | — |
| version (version) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| snapshot (snapshot) | JSONField / text | 예 / False | 없음 | — |
| file (file) | FileField(100) / varchar(100) | 예 / False | 없음 | — |
| bundle (bundle) | FileField(100) / varchar(100) | 예 / True | 없음 | — |
| sha256 (sha256) | CharField(64) / varchar(64) | 예 / False | 없음 | — |
| bundle_sha256 (bundle_sha256) | CharField(64) / varchar(64) | 예 / True | 없음 | — |
| generated_by (generated_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| generated_at (generated_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: version
- <UniqueConstraint: fields=('complaint', 'version') name='unique_report_artifact_version'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## LoginBucket — `pms_loginbucket`

로그인 제한 버킷.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| key (key) | CharField(64) / varchar(64) | 예 / False | 없음 | — |
| count (count) | PositiveIntegerField / integer unsigned | 예 / False | 0 | — |
| expires_at (expires_at) | DateTimeField / datetime | 예 / False | 없음 | — |

DB 제약:

- PK/필드 unique: id, key
- unique_together: []
- 타입의 암묵적 DB 비음수 CHECK: count

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## RegulationDocument — `pms_regulationdocument`

규정 원본·검토.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| issuer (issuer) | CharField(200) / varchar(200) | 예 / False | 없음 | — |
| jurisdiction (jurisdiction) | CharField(120) / varchar(120) | 예 / False | 없음 | — |
| device (device_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_medicaldevice.id / PROTECT |
| scope_description (scope_description) | TextField / text | 예 / False | 없음 | — |
| document_number (document_number) | CharField(160) / varchar(160) | 예 / False | 없음 | — |
| edition (edition) | CharField(120) / varchar(120) | 예 / False | 없음 | — |
| published_on (published_on) | DateField / date | 아니오 / True | 없음 | — |
| effective_on (effective_on) | DateField / date | 아니오 / True | 없음 | — |
| official_url (official_url) | CharField(1000) / varchar(1000) | 예 / True | 없음 | — |
| file (file) | FileField(255) / varchar(255) | 예 / False | 없음 | — |
| original_name (original_name) | CharField(255) / varchar(255) | 예 / True | 없음 | — |
| uploaded_by (uploaded_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| visibility (visibility) | CharField(12) / varchar(12) | 예 / False | 'TEAM' | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| scan_status (scan_status) | CharField(12) / varchar(12) | 예 / False | 'PENDING' | — |
| sha256 (sha256) | CharField(64) / varchar(64) | 예 / True | 없음 | — |
| detected_type (detected_type) | CharField(20) / varchar(20) | 예 / True | 없음 | — |
| scanned_at (scanned_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| extraction_status (extraction_status) | CharField(16) / varchar(16) | 예 / False | 'PENDING' | — |
| extraction_note (extraction_note) | CharField(300) / varchar(300) | 예 / True | 없음 | — |
| review_status (review_status) | CharField(12) / varchar(12) | 예 / False | 'UNREVIEWED' | — |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| review_reason (review_reason) | TextField / text | 예 / True | 없음 | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: pms_regulat_jurisdi_148d3d_idx: ['jurisdiction', 'document_number', 'edition']

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.
- `visibility` 허용값: TEAM, PRIVATE
- `scan_status` 허용값: PENDING, PASSED, QUARANTINED, FAILED
- `extraction_status` 허용값: PENDING, READY, OCR_REQUIRED, FAILED, BLOCKED
- `review_status` 허용값: UNREVIEWED, REVIEWED, REJECTED

## RegulationChunk — `pms_regulationchunk`

원문 청크.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| document (document_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulationdocument.id / PROTECT |
| sequence (sequence) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| page (page) | PositiveIntegerField / integer unsigned | 아니오 / True | 없음 | — |
| section (section) | CharField(240) / varchar(240) | 예 / True | 없음 | — |
| paragraph (paragraph) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| text (text) | TextField / text | 예 / False | 없음 | — |
| content_hash (content_hash) | CharField(64) / varchar(64) | 예 / False | 없음 | — |
| search_tokens (search_tokens) | JSONField / text | 예 / False | list | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: sequence, page, paragraph
- <UniqueConstraint: fields=('document', 'sequence') name='unique_document_chunk'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## RuleCitation — `pms_rulecitation`

규칙 항목과 원문 인용.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| rule (rule_id) | ForeignKey / bigint | 예 / False | 없음 | pms_reportingrule.id / PROTECT |
| field_name (field_name) | CharField(80) / varchar(80) | 예 / False | 없음 | — |
| chunk (chunk_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulationchunk.id / PROTECT |
| quote (quote) | TextField / text | 예 / False | 없음 | — |
| interpretation (interpretation) | TextField / text | 예 / True | 없음 | — |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

DB 제약:

- PK/필드 unique: id
- unique_together: []

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## RulePreview — `pms_rulepreview`

기한 미리보기.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| rule (rule_id) | ForeignKey / bigint | 예 / False | 없음 | pms_reportingrule.id / PROTECT |
| fingerprint (fingerprint) | CharField(64) / varchar(64) | 예 / False | 없음 | — |
| inputs (inputs) | JSONField / text | 예 / False | 없음 | — |
| result (result) | JSONField / text | 예 / False | 없음 | — |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## RuleChange — `pms_rulechange`

규칙 변경 이력.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| rule (rule_id) | ForeignKey / bigint | 예 / False | 없음 | pms_reportingrule.id / PROTECT |
| actor (actor_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| action (action) | CharField(30) / varchar(30) | 예 / False | 없음 | — |
| reason (reason) | TextField / text | 예 / False | 없음 | — |
| before (before) | JSONField / text | 예 / True | dict | — |
| after (after) | JSONField / text | 예 / True | dict | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## RuleFamilyLock — `pms_rulefamilylock`

규칙 계열 직렬화 잠금.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| key (key) PK | UUIDField(32) / char(32) | 예 / False | uuid4 | — |

DB 제약:

- PK/필드 unique: key
- unique_together: []

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## AnalysisImport — `pms_analysisimport`

분석 원본 CSV 수집.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| filename (filename) | CharField(255) / varchar(255) | 예 / False | 없음 | — |
| original (original) | BinaryField / BLOB | 예 / False | 없음 | — |
| sha256 (sha256) | CharField(64) / varchar(64) | 예 / False | 없음 | — |
| actor (actor_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| errors (errors) | JSONField / text | 예 / False | list | — |
| accepted (accepted) | PositiveIntegerField / integer unsigned | 예 / False | 0 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

DB 제약:

- PK/필드 unique: id
- unique_together: []
- 타입의 암묵적 DB 비음수 CHECK: accepted

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## AnalysisRecord — `pms_analysisrecord`

출처별 정규화 레코드.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| batch (batch_id) | ForeignKey / bigint | 예 / False | 없음 | pms_analysisimport.id / PROTECT |
| row_number (row_number) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| raw (raw) | JSONField / text | 예 / False | 없음 | — |
| source (source) | CharField(200) / varchar(200) | 예 / False | 없음 | — |
| record_id (record_id) | CharField(200) / varchar(200) | 예 / True | 없음 | — |
| identity (identity) | CharField(64) / varchar(64) | 예 / False | 없음 | — |
| device (device) | CharField(200) / varchar(200) | 예 / False | 없음 | — |
| manufacturer (manufacturer) | CharField(200) / varchar(200) | 예 / True | 없음 | — |
| model (model) | CharField(200) / varchar(200) | 예 / True | 없음 | — |
| occurred_on (occurred_on) | DateField / date | 아니오 / False | 없음 | — |
| reported_on (reported_on) | DateField / date | 예 / False | 없음 | — |
| event_type (event_type) | CharField(200) / varchar(200) | 예 / False | 없음 | — |
| seriousness (seriousness) | CharField(12) / varchar(12) | 예 / False | 없음 | — |
| narrative (narrative) | TextField / text | 예 / True | 없음 | — |

DB 제약:

- PK/필드 unique: id, identity
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: row_number
- <UniqueConstraint: fields=('batch', 'row_number') name='unique_import_row'>
- <CheckConstraint: condition=(AND: ('seriousness__in', ['SERIOUS', 'NON_SERIOUS', 'UNKNOWN'])) name='analysis_seriousness_valid'>

명시 인덱스: analysis_reported_period: ['reported_on']; analysis_occurred_period: ['occurred_on']

앱/서비스 조건: analysis.ingest: CSV·날짜·내용 검증, 실제/예시를 포함한 identity. unique 충돌은 행 오류로 보존.
- `seriousness` 허용값: SERIOUS, NON_SERIOUS, UNKNOWN

## AnalysisReview — `pms_analysisreview`

분석 신호 검토.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| key (key) | CharField(64) / varchar(64) | 예 / False | 없음 | — |
| snapshot (snapshot) | JSONField / text | 예 / False | 없음 | — |
| status (status) | CharField(12) / varchar(12) | 예 / False | 'NEW' | — |
| assignee (assignee_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |

DB 제약:

- PK/필드 unique: id, key
- unique_together: []

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.
- `status` 허용값: NEW, REVIEW, ACTION, CLOSED

## AnalysisReviewHistory — `pms_analysisreviewhistory`

분석 검토 이력.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| review (review_id) | ForeignKey / bigint | 예 / False | 없음 | pms_analysisreview.id / PROTECT |
| actor (actor_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| assignee (assignee_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| before (before) | CharField(12) / varchar(12) | 예 / True | 없음 | — |
| after (after) | CharField(12) / varchar(12) | 예 / False | 없음 | — |
| note (note) | TextField / text | 예 / False | 없음 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SafetySignal — `pms_safetysignal`

내부 사건 안전 신호.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| key (key) | CharField(64) / varchar(64) | 예 / False | 없음 | — |
| scope (scope) | CharField(80) / varchar(80) | 예 / False | 없음 | — |
| snapshot (snapshot) | JSONField / text | 예 / False | 없음 | — |
| status (status) | CharField(12) / varchar(12) | 예 / False | 'NEW' | — |
| assignee (assignee_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| task (task_id) | OneToOneField / bigint | 아니오 / False | 없음 | pms_worktask.id / PROTECT |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

DB 제약:

- PK/필드 unique: id, key, task
- unique_together: ()
- <CheckConstraint: condition=(AND: ('status__in', ['NEW', 'REVIEW', 'ACTION', 'CLOSED'])) name='signal_status_valid'>

명시 인덱스: signal_scope_sequence: ['scope', '-id']

앱/서비스 조건: safety.detect: scope+필터+규칙 버전+제품·LOT로 key 해시. review_signal: 활성 전문 역할, 증거 사건에 속한 CAPA·리콜 연결.
- `status` 허용값: NEW, REVIEW, ACTION, CLOSED

## SafetyReview — `pms_safetyreview`

안전 신호 검토 이력.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| signal (signal_id) | ForeignKey / bigint | 예 / False | 없음 | pms_safetysignal.id / PROTECT |
| actor (actor_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| assignee (assignee_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| before (before) | CharField(12) / varchar(12) | 예 / False | 없음 | — |
| after (after) | CharField(12) / varchar(12) | 예 / False | 없음 | — |
| note (note) | TextField / text | 예 / False | 없음 | — |
| links (links) | JSONField / text | 예 / False | dict | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## RegulatoryImpact — `pms_regulatoryimpact`

개정 영향 분석.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| old_rule (old_rule_id) | ForeignKey / bigint | 예 / False | 없음 | pms_reportingrule.id / PROTECT |
| new_rule (new_rule_id) | ForeignKey / bigint | 예 / False | 없음 | pms_reportingrule.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| snapshot (snapshot) | JSONField / text | 예 / False | 없음 | — |
| include_closed (include_closed) | BooleanField / bool | 예 / False | False | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ImpactReview — `pms_impactreview`

사건별 영향 처리.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| analysis (analysis_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryimpact.id / PROTECT |
| complaint (complaint_id) | ForeignKey / bigint | 예 / False | 없음 | pms_customercomplaint.id / PROTECT |
| task (task_id) | OneToOneField / bigint | 예 / False | 없음 | pms_worktask.id / PROTECT |
| status (status) | CharField(16) / varchar(16) | 예 / False | 'WAITING' | — |
| snapshot (snapshot) | JSONField / text | 예 / False | 없음 | — |
| shortened (shortened) | BooleanField / bool | 예 / False | False | — |
| reason (reason) | TextField / text | 예 / True | 없음 | — |
| processed_by (processed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| processed_at (processed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| application (application_id) | OneToOneField / bigint | 아니오 / True | 없음 | pms_ruleapplication.id / PROTECT |

DB 제약:

- PK/필드 unique: id, task, application
- unique_together: ()
- <CheckConstraint: condition=(AND: ('status__in', ['WAITING', 'IN_PROGRESS', 'APPLIED', 'EXCLUDED'])) name='impactreview_status_valid'>
- <UniqueConstraint: fields=('analysis', 'complaint') name='unique_impact_case'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 서비스의 분석 토큰·사유·권한 검사; 모델은 업무·적용 사건·규칙 연결 검사.
- `status` 허용값: WAITING, IN_PROGRESS, APPLIED, EXCLUDED

## RiskAssessmentHistory — `pms_riskassessmenthistory`

이번 추가: 실제 저장 시점 위험평가 변경 기록.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| actor (actor_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| reason (reason) | TextField / text | 예 / True | 없음 | — |
| source (source) | CharField(20) / varchar(20) | 예 / False | 없음 | — |
| before (before) | JSONField / text | 예 / False | dict | — |
| after (after) | JSONField / text | 예 / False | dict | — |
| parent (parent_id) | ForeignKey / bigint | 예 / False | 없음 | pms_riskassessment.id / PROTECT |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: risk_history_parent_time: ['parent', 'created_at']

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.
- `source` 허용값: APPLICATION, DIRECT_MODEL

## RegulatoryReportHistory — `pms_regulatoryreporthistory`

이번 추가: 실제 저장 시점 규제보고 변경 기록.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| actor (actor_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| reason (reason) | TextField / text | 예 / True | 없음 | — |
| source (source) | CharField(20) / varchar(20) | 예 / False | 없음 | — |
| before (before) | JSONField / text | 예 / False | dict | — |
| after (after) | JSONField / text | 예 / False | dict | — |
| parent (parent_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryreport.id / PROTECT |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: report_history_parent_time: ['parent', 'created_at']

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.
- `source` 허용값: APPLICATION, DIRECT_MODEL

## RegulatoryProfile — `pms_regulatoryprofile`

제품·관할·조직 역할의 적용 범위와 근거.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| device (device_id) | ForeignKey / bigint | 예 / False | 없음 | pms_medicaldevice.id / PROTECT |
| jurisdiction (jurisdiction) | CharField(120) / varchar(120) | 예 / False | 없음 | — |
| organization (organization_id) | ForeignKey / bigint | 예 / False | 없음 | pms_businesspartner.id / PROTECT |
| organization_role (organization_role) | CharField(30) / varchar(30) | 예 / False | 없음 | — |
| product_family (product_family) | CharField(160) / varchar(160) | 예 / True | 없음 | — |
| classification (classification) | CharField(100) / varchar(100) | 예 / True | 없음 | — |
| classification_basis (classification_basis) | TextField / text | 예 / True | 없음 | — |
| intended_use (intended_use) | TextField / text | 예 / True | 없음 | — |
| authorized_scope (authorized_scope) | TextField / text | 예 / True | 없음 | — |
| applicability (applicability) | CharField(20) / varchar(20) | 예 / False | 'UNVERIFIED' | — |
| rationale (rationale) | TextField / text | 예 / True | 없음 | — |
| source (source_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_regulationdocument.id / PROTECT |
| source_url (source_url) | CharField(1000) / varchar(1000) | 예 / True | 없음 | — |
| source_checked_on (source_checked_on) | DateField / date | 아니오 / True | 없음 | — |
| source_checked_by (source_checked_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| effective_on (effective_on) | DateField / date | 아니오 / True | 없음 | — |
| next_review_on (next_review_on) | DateField / date | 아니오 / True | 없음 | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='regulatoryprofile_state_valid'>
- <UniqueConstraint: fields=('device', 'jurisdiction', 'organization', 'organization_role', 'is_example') name='unique_ra_profile'>
- <CheckConstraint: condition=(AND: ('organization_role__in', ['MANUFACTURER', 'IMPORTER', 'DISTRIBUTOR', 'OTHER'])) name='ra_regulatoryprofile_organization_role_valid'>
- <CheckConstraint: condition=(AND: ('applicability__in', ['UNVERIFIED', 'APPLIES', 'NOT_APPLICABLE'])) name='ra_regulatoryprofile_applicability_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 범위는 변경 불가. 적용·비적용은 출처·확인자·확인일·사유 요구. 법적 판단은 담당자 입력.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `organization_role` 허용값: MANUFACTURER, IMPORTER, DISTRIBUTOR, OTHER
- `applicability` 허용값: UNVERIFIED, APPLIES, NOT_APPLICABLE

## RARequirement — `pms_rarequirement`

근거 조항·활동·증빙·충족 및 정기 검토 매트릭스.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| internal_id (internal_id) | CharField(80) / varchar(80) | 예 / False | 없음 | — |
| source (source_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_regulationdocument.id / PROTECT |
| clause (clause_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_regulationchunk.id / PROTECT |
| clause_reference (clause_reference) | CharField(240) / varchar(240) | 예 / True | 없음 | — |
| applicability (applicability) | CharField(20) / varchar(20) | 예 / False | 'UNVERIFIED' | — |
| applicability_reason (applicability_reason) | TextField / text | 예 / True | 없음 | — |
| activity (activity) | TextField / text | 예 / False | 없음 | — |
| deliverable (deliverable) | TextField / text | 예 / True | 없음 | — |
| fulfillment (fulfillment) | CharField(20) / varchar(20) | 예 / False | 'UNVERIFIED' | — |
| due_on (due_on) | DateField / date | 아니오 / True | 없음 | — |
| review_interval_days (review_interval_days) | PositiveIntegerField / integer unsigned | 아니오 / True | 없음 | — |
| confirmed_on (confirmed_on) | DateField / date | 아니오 / True | 없음 | — |
| next_review_on (next_review_on) | DateField / date | 아니오 / True | 없음 | — |
| source_url (source_url) | CharField(1000) / varchar(1000) | 예 / True | 없음 | — |
| source_checked_on (source_checked_on) | DateField / date | 아니오 / True | 없음 | — |
| source_checked_by (source_checked_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_rarequirement_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_rarequirement_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision, review_interval_days
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='rarequirement_state_valid'>
- <UniqueConstraint: fields=('profile', 'internal_id') name='unique_ra_requirement'>
- <CheckConstraint: condition=(AND: ('fulfillment__in', ['UNVERIFIED', 'IN_REVIEW', 'MET', 'NOT_MET', 'NOT_APPLICABLE'])) name='requirement_fulfillment_valid'>
- <CheckConstraint: condition=(AND: ('applicability__in', ['UNVERIFIED', 'APPLIES', 'NOT_APPLICABLE'])) name='ra_rarequirement_applicability_valid'>

명시 인덱스: ra_requirement_due: ['profile', 'fulfillment', 'due_on']

앱/서비스 조건: 원문·청크 버전 일치, 실제/예시 분리, 적용·충족 사유와 검토일 검증.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `applicability` 허용값: UNVERIFIED, APPLIES, NOT_APPLICABLE
- `fulfillment` 허용값: UNVERIFIED, IN_REVIEW, MET, NOT_MET, NOT_APPLICABLE

## MarketingAuthorization — `pms_marketingauthorization`

수동 확인 인허가·갱신과 외부 상태 기록.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| kind (kind) | CharField(100) / varchar(100) | 예 / False | 없음 | — |
| number (number) | CharField(160) / varchar(160) | 예 / True | 없음 | — |
| authority (authority) | CharField(240) / varchar(240) | 예 / True | 없음 | — |
| issued_on (issued_on) | DateField / date | 아니오 / True | 없음 | — |
| expires_on (expires_on) | DateField / date | 아니오 / True | 없음 | — |
| conditions (conditions) | TextField / text | 예 / True | 없음 | — |
| status (status) | CharField(20) / varchar(20) | 예 / False | 'UNKNOWN' | — |
| renewal_prepare_on (renewal_prepare_on) | DateField / date | 아니오 / True | 없음 | — |
| renewal_basis (renewal_basis) | TextField / text | 예 / True | 없음 | — |
| verified_on (verified_on) | DateField / date | 아니오 / True | 없음 | — |
| verification_source (verification_source) | CharField(1000) / varchar(1000) | 예 / True | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_marketingauthorization_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_marketingauthorization_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='marketingauthorization_state_valid'>
- <CheckConstraint: condition=(OR: ('expires_on__isnull', True), ('issued_on__isnull', True), ('expires_on__gte', F(issued_on))) name='authorization_date_order'>
- <CheckConstraint: condition=(AND: ('status__in', ['UNKNOWN', 'APPLICATION', 'SUPPLEMENT', 'APPROVED', 'REJECTED', 'WITHDRAWN', 'EXPIRED', 'SUSPENDED', 'REVOKED'])) name='ra_marketingauthoriza_status_valid'>

명시 인덱스: ra_authorization_expiry: ['profile', 'status', 'expires_on']

앱/서비스 조건: 승인 기록은 번호·기관·확인일·출처 필요. 상태 변경은 AuthorizationEvent. 만료일이나 갱신주기 자동 추정 없음.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `status` 허용값: UNKNOWN, APPLICATION, SUPPLEMENT, APPROVED, REJECTED, WITHDRAWN, EXPIRED, SUSPENDED, REVOKED

## AuthorizationEvent — `pms_authorizationevent`

허가 신청·보완·승인 등 실제 기록 시점의 상태 이력.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| authorization (authorization_id) | ForeignKey / bigint | 예 / False | 없음 | pms_marketingauthorization.id / PROTECT |
| status (status) | CharField(20) / varchar(20) | 예 / False | 없음 | — |
| reason (reason) | TextField / text | 예 / False | 없음 | — |
| actor (actor_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| snapshot (snapshot) | JSONField / text | 예 / False | 없음 | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: ra_authorization_event_time: ['authorization', 'created_at']

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SubmissionPackage — `pms_submissionpackage`

허가별 제출 파일·접수 증빙·제품 버전의 승인 스냅샷.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| product_revision (product_revision_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_productrevision.id / PROTECT |
| change (change_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_productchange.id / PROTECT |
| authorization (authorization_id) | ForeignKey / bigint | 예 / False | 없음 | pms_marketingauthorization.id / PROTECT |
| version (version) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| content_description (content_description) | TextField / text | 예 / False | 없음 | — |
| receipt_reference (receipt_reference) | CharField(240) / varchar(240) | 예 / True | 없음 | — |
| receipt (receipt_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_attachment.id / PROTECT |
| recorded_submitted_on (recorded_submitted_on) | DateField / date | 아니오 / True | 없음 | — |
| frozen_snapshot (frozen_snapshot) | JSONField / text | 예 / True | dict | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_submissionpackage_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_submissionpackage_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision, version
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='submissionpackage_state_valid'>
- <UniqueConstraint: fields=('authorization', 'version') name='unique_submission_package'>
- <CheckConstraint: condition=(AND: ('version__gte', 1)) name='submission_positive_version'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 프로필·허가·제품 버전·변경·파일 일치, 승인 목록/해시 고정. ZIP 다운로드 시 해시 재검증.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## ProductRevision — `pms_productrevision`

제품 구성 버전과 이전 버전 관계.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| version (version) | CharField(80) / varchar(80) | 예 / False | 없음 | — |
| description (description) | TextField / text | 예 / False | 없음 | — |
| previous (previous_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_productrevision.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_productrevision_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_productrevision_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='productrevision_state_valid'>
- <UniqueConstraint: fields=('profile', 'version') name='unique_product_revision'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 같은 프로필의 제품 버전·이전 버전. 승인된 내용은 서비스에서 수정 금지.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## ControlledDocument — `pms_controlleddocument`

SOP 등 내부 통제 문서의 개정·시행본.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| category (category) | CharField(12) / varchar(12) | 예 / False | 없음 | — |
| number (number) | CharField(80) / varchar(80) | 예 / False | 없음 | — |
| version (version) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| body (body) | TextField / text | 예 / True | 없음 | — |
| primary_file (primary_file_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_attachment.id / PROTECT |
| effective_on (effective_on) | DateField / date | 아니오 / True | 없음 | — |
| next_review_on (next_review_on) | DateField / date | 아니오 / True | 없음 | — |
| change_reason (change_reason) | TextField / text | 예 / False | 없음 | — |
| supersedes (supersedes_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_controlleddocument.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_controlleddocument_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_controlleddocument_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision, version
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='controlleddocument_state_valid'>
- <UniqueConstraint: fields=('profile', 'number', 'version') name='unique_controlled_document'>
- <UniqueConstraint: fields=('profile', 'number') name='one_effective_controlled_doc' condition=(AND: ('state', 'EFFECTIVE'))>
- <CheckConstraint: condition=(AND: ('version__gte', 1)) name='controlled_doc_positive_version'>
- <CheckConstraint: condition=(AND: ('category__in', ['SOP', 'INSTRUCTION', 'FORM', 'TECHNICAL'])) name='ra_controlleddocument_category_valid'>

명시 인덱스: ra_document_review: ['profile', 'state', 'next_review_on']

앱/서비스 조건: 본문 또는 검사 통과 파일, 버전 계열, 시행일·대체 버전·현재 시행본 검사. 승인 후 새 개정 필요.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `category` 허용값: SOP, INSTRUCTION, FORM, TECHNICAL

## ProductChange — `pms_productchange`

제품 변경 전후·영향 평가·추가 제출 판단·시행 확인.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| category (category) | CharField(16) / varchar(16) | 예 / False | 없음 | — |
| from_revision (from_revision_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productrevision.id / PROTECT |
| to_revision (to_revision_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productrevision.id / PROTECT |
| before_content (before_content) | TextField / text | 예 / False | 없음 | — |
| after_content (after_content) | TextField / text | 예 / False | 없음 | — |
| reason (reason) | TextField / text | 예 / False | 없음 | — |
| impact_checklist (impact_checklist) | JSONField / text | 예 / True | dict | — |
| submission_decision (submission_decision) | CharField(16) / varchar(16) | 예 / False | 'UNVERIFIED' | — |
| decision_basis (decision_basis) | TextField / text | 예 / True | 없음 | — |
| authorization (authorization_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_marketingauthorization.id / PROTECT |
| implemented_on (implemented_on) | DateField / date | 아니오 / True | 없음 | — |
| implementation_confirmation (implementation_confirmation) | TextField / text | 예 / True | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_productchange_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_productchange_tasks`, 두 필수 FK 및 쌍 unique.

N:M `lots` → `pms_productlot`, 실제 중간 테이블 `pms_productchange_lots`, 두 필수 FK 및 쌍 unique.

N:M `documents` → `pms_controlleddocument`, 실제 중간 테이블 `pms_productchange_documents`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='productchange_state_valid'>
- <CheckConstraint: condition=(AND: ('category__in', ['DESIGN', 'MATERIAL', 'SUPPLIER', 'PROCESS', 'SOFTWARE', 'LABEL'])) name='ra_productchange_category_valid'>
- <CheckConstraint: condition=(AND: ('submission_decision__in', ['UNVERIFIED', 'REQUIRED', 'NOT_REQUIRED'])) name='ra_productchange_submission_decisi_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 전후 제품 버전, LOT, 6개 영역 영향 판단, 제출 판단 근거, 승인 해시·업무 완료 검증 후 실제 시행 기록.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `category` 허용값: DESIGN, MATERIAL, SUPPLIER, PROCESS, SOFTWARE, LABEL
- `submission_decision` 허용값: UNVERIFIED, REQUIRED, NOT_REQUIRED

## LabelVersion — `pms_labelversion`

제품·관할·언어별 라벨/설명서와 번역 검토.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| artifact_type (artifact_type) | CharField(8) / varchar(8) | 예 / False | 없음 | — |
| language (language) | CharField(60) / varchar(60) | 예 / False | 없음 | — |
| version (version) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| document (document_id) | ForeignKey / bigint | 예 / False | 없음 | pms_controlleddocument.id / PROTECT |
| product_revision (product_revision_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productrevision.id / PROTECT |
| authorization (authorization_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_marketingauthorization.id / PROTECT |
| change (change_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_productchange.id / PROTECT |
| udi (udi_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_udi.id / PROTECT |
| review_checklist (review_checklist) | JSONField / text | 예 / True | dict | — |
| translation_reviewer (translation_reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| translation_reviewed_on (translation_reviewed_on) | DateField / date | 아니오 / True | 없음 | — |
| translation_notes (translation_notes) | TextField / text | 예 / True | 없음 | — |
| effective_on (effective_on) | DateField / date | 아니오 / True | 없음 | — |
| previous (previous_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_labelversion.id / PROTECT |
| safety_action (safety_action_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_fieldsafetyaction.id / PROTECT |
| safety_change_reason (safety_change_reason) | TextField / text | 예 / True | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_labelversion_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_labelversion_tasks`, 두 필수 FK 및 쌍 unique.

N:M `lots` → `pms_productlot`, 실제 중간 테이블 `pms_labelversion_lots`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision, version
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='labelversion_state_valid'>
- <UniqueConstraint: fields=('profile', 'artifact_type', 'language', 'version') name='unique_label_version'>
- <UniqueConstraint: fields=('profile', 'artifact_type', 'language') name='one_effective_label' condition=(AND: ('state', 'EFFECTIVE'))>
- <CheckConstraint: condition=(AND: ('version__gte', 1)) name='label_positive_version'>
- <CheckConstraint: condition=(AND: ('artifact_type__in', ['LABEL', 'IFU'])) name='ra_labelversion_artifact_type_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 제품·UDI·LOT·문서 버전·현장 조치 범위 일치. 담당 번역 검토와 표시 체크리스트 없으면 승인 차단.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `artifact_type` 허용값: LABEL, IFU

## RiskCriteria — `pms_riskcriteria`

제품별 위험 추정·수용 기준 버전.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| version (version) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| estimation_method (estimation_method) | TextField / text | 예 / False | 없음 | — |
| acceptance_criteria (acceptance_criteria) | TextField / text | 예 / False | 없음 | — |
| basis (basis) | TextField / text | 예 / False | 없음 | — |
| document (document_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_controlleddocument.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_riskcriteria_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_riskcriteria_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision, version
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='riskcriteria_state_valid'>
- <UniqueConstraint: fields=('profile', 'version') name='unique_risk_criteria_version'>
- <CheckConstraint: condition=(AND: ('version__gte', 1)) name='riskcriteria_positive_version'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 제품별 수용 기준의 담당자 승인, 사건 위험 점수 자동 적용 없음.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## ProductRisk — `pms_productrisk`

위해·통제 검증·잔여위험·편익 위험 판단.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| criteria (criteria_id) | ForeignKey / bigint | 예 / False | 없음 | pms_riskcriteria.id / PROTECT |
| document (document_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_controlleddocument.id / PROTECT |
| hazard (hazard) | TextField / text | 예 / False | 없음 | — |
| hazardous_situation (hazardous_situation) | TextField / text | 예 / False | 없음 | — |
| harm (harm) | TextField / text | 예 / False | 없음 | — |
| estimate (estimate) | TextField / text | 예 / False | 없음 | — |
| controls (controls) | TextField / text | 예 / True | 없음 | — |
| verification (verification) | TextField / text | 예 / True | 없음 | — |
| residual_decision (residual_decision) | CharField(20) / varchar(20) | 예 / False | 'UNVERIFIED' | — |
| residual_rationale (residual_rationale) | TextField / text | 예 / True | 없음 | — |
| benefit_risk_rationale (benefit_risk_rationale) | TextField / text | 예 / True | 없음 | — |
| next_review_on (next_review_on) | DateField / date | 아니오 / True | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_productrisk_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_productrisk_tasks`, 두 필수 FK 및 쌍 unique.

N:M `complaints` → `pms_customercomplaint`, 실제 중간 테이블 `pms_productrisk_complaints`, 두 필수 FK 및 쌍 unique.

N:M `adverse_events` → `pms_adverseevent`, 실제 중간 테이블 `pms_productrisk_adverse_events`, 두 필수 FK 및 쌍 unique.

N:M `signals` → `pms_safetysignal`, 실제 중간 테이블 `pms_productrisk_signals`, 두 필수 FK 및 쌍 unique.

N:M `capas` → `pms_capa`, 실제 중간 테이블 `pms_productrisk_capas`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='productrisk_state_valid'>
- <CheckConstraint: condition=(AND: ('residual_decision__in', ['UNVERIFIED', 'ACCEPTABLE', 'NOT_ACCEPTABLE'])) name='ra_productrisk_residual_decision_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 승인된 수용 기준, 잔여위험·편익 판단·검증 파일. PMS 관계의 제품/예시 범위 검사.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `residual_decision` 허용값: UNVERIFIED, ACCEPTABLE, NOT_ACCEPTABLE

## SafetyInformation — `pms_safetyinformation`

외부 안전성 정보 수동 수집·연관성 및 보고 검토.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| source_url (source_url) | CharField(1000) / varchar(1000) | 예 / False | 없음 | — |
| source_identifier (source_identifier) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| collected_on (collected_on) | DateField / date | 예 / False | localdate | — |
| original (original_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_attachment.id / PROTECT |
| relevance (relevance) | CharField(16) / varchar(16) | 예 / False | 'UNVERIFIED' | — |
| relevance_reason (relevance_reason) | TextField / text | 예 / True | 없음 | — |
| reporting_decision (reporting_decision) | CharField(16) / varchar(16) | 예 / False | 'UNVERIFIED' | — |
| reporting_basis (reporting_basis) | TextField / text | 예 / True | 없음 | — |
| report (report_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_regulatoryreport.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_safetyinformation_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_safetyinformation_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='safetyinformation_state_valid'>
- <UniqueConstraint: fields=('profile', 'source_url', 'source_identifier') name='unique_external_safety_source'>
- <CheckConstraint: condition=(AND: ('relevance__in', ['UNVERIFIED', 'RELATED', 'UNRELATED'])) name='ra_safetyinformation_relevance_valid'>
- <CheckConstraint: condition=(AND: ('reporting_decision__in', ['UNVERIFIED', 'REQUIRED', 'NOT_REQUIRED'])) name='ra_safetyinformation_reporting_decisio_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: URL/외부 식별자 중복 방지. 보고·연관성 수동 판단과 이유 보존.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `relevance` 허용값: UNVERIFIED, RELATED, UNRELATED
- `reporting_decision` 허용값: UNVERIFIED, REQUIRED, NOT_REQUIRED

## FieldSafetyAction — `pms_fieldsafetyaction`

승인 안내문 기반 고객 안내·현장 수정·기존 리콜 연결.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| action_type (action_type) | CharField(16) / varchar(16) | 예 / False | 없음 | — |
| information (information_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_safetyinformation.id / PROTECT |
| complaint (complaint_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_customercomplaint.id / PROTECT |
| signal (signal_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_safetysignal.id / PROTECT |
| capa (capa_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_capa.id / PROTECT |
| recall (recall_id) | OneToOneField / bigint | 아니오 / True | 없음 | pms_recall.id / PROTECT |
| notice_document (notice_document_id) | ForeignKey / bigint | 예 / False | 없음 | pms_controlleddocument.id / PROTECT |
| rationale (rationale) | TextField / text | 예 / False | 없음 | — |
| effectiveness_criteria (effectiveness_criteria) | TextField / text | 예 / True | 없음 | — |
| closure_rationale (closure_rationale) | TextField / text | 예 / True | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_fieldsafetyaction_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_fieldsafetyaction_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id, recall
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='fieldsafetyaction_state_valid'>
- <CheckConstraint: condition=(OR: (AND: ('action_type', 'RECALL'), ('recall__isnull', False)), (AND: (NOT (AND: ('action_type', 'RECALL'))), ('recall__isnull', True))) name='field_action_recall_context'>
- <CheckConstraint: condition=(AND: ('action_type__in', ['NOTICE', 'CORRECTION', 'RECALL'])) name='ra_fieldsafetyaction_action_type_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 승인된 안내문·효과 기준, 회수는 기존 원장. 최신 효과 평가·대상·업무 검토 후 종결.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `action_type` 허용값: NOTICE, CORRECTION, RECALL

## FieldActionRecipient — `pms_fieldactionrecipient`

비회수 조치의 거래처·LOT 대상과 완료 수량.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| action (action_id) | ForeignKey / bigint | 예 / False | 없음 | pms_fieldsafetyaction.id / PROTECT |
| partner (partner_id) | ForeignKey / bigint | 예 / False | 없음 | pms_businesspartner.id / PROTECT |
| lot (lot_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productlot.id / PROTECT |
| unit (unit) | CharField(20) / varchar(20) | 예 / False | '개' | — |
| target_quantity (target_quantity) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| completed_quantity (completed_quantity) | PositiveIntegerField / integer unsigned | 예 / False | 0 | — |
| notified_on (notified_on) | DateField / date | 아니오 / True | 없음 | — |
| acknowledged_on (acknowledged_on) | DateField / date | 아니오 / True | 없음 | — |
| completed_on (completed_on) | DateField / date | 아니오 / True | 없음 | — |
| outcome (outcome) | TextField / text | 예 / True | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_fieldactionrecipient_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_fieldactionrecipient_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision, target_quantity, completed_quantity
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='fieldactionrecipient_state_valid'>
- <UniqueConstraint: fields=('action', 'partner', 'lot', 'unit') name='unique_field_action_recipient'>
- <CheckConstraint: condition=(AND: ('completed_quantity__lte', F(target_quantity)), ('target_quantity__gte', 1)) name='field_recipient_quantity'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 회수 조치는 금지. 승인된 대상 계획 고정, 시행 중 완료일·근거와 완료 누계를 기록.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## FieldActionContact — `pms_fieldactioncontact`

현장 조치의 수동 후속 연락 사실.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| recipient (recipient_id) | ForeignKey / bigint | 예 / False | 없음 | pms_fieldactionrecipient.id / PROTECT |
| actor (actor_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| contacted_at (contacted_at) | DateTimeField / datetime | 예 / False | now | — |
| method (method) | CharField(120) / varchar(120) | 예 / False | 없음 | — |
| note (note) | TextField / text | 예 / False | 없음 | — |
| evidence (evidence_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_attachment.id / PROTECT |

DB 제약:

- PK/필드 unique: id
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 시행 중 비회수 조치의 수동 연락만 기록.

## FieldActionEvaluation — `pms_fieldactionevaluation`

현장 조치 효과·근거의 추가 평가 기록.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| action (action_id) | ForeignKey / bigint | 예 / False | 없음 | pms_fieldsafetyaction.id / PROTECT |
| actor (actor_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| evaluated_at (evaluated_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| verdict (verdict) | CharField(12) / varchar(12) | 예 / False | 없음 | — |
| rationale (rationale) | TextField / text | 예 / False | 없음 | — |
| evidence (evidence_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / PROTECT |
| snapshot (snapshot) | JSONField / text | 예 / False | 없음 | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- <CheckConstraint: condition=(AND: ('verdict__in', ['EFFECTIVE', 'INEFFECTIVE'])) name='ra_fieldactionevaluat_verdict_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 시행 중 승인 조치에 검사 통과 증빙과 판정·근거를 추가.
- `verdict` 허용값: EFFECTIVE, INEFFECTIVE

## SupplierRecord — `pms_supplierrecord`

기존 거래처의 공급자·제조소·위탁 범위 및 조직 평가 기준.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| partner (partner_id) | ForeignKey / bigint | 예 / False | 없음 | pms_businesspartner.id / PROTECT |
| supplier_type (supplier_type) | CharField(20) / varchar(20) | 예 / False | 없음 | — |
| site_reference (site_reference) | CharField(240) / varchar(240) | 예 / True | 없음 | — |
| process_service (process_service) | TextField / text | 예 / False | 없음 | — |
| evaluation_criteria (evaluation_criteria) | TextField / text | 예 / False | 없음 | — |
| criteria_document (criteria_document_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_controlleddocument.id / PROTECT |
| next_review_on (next_review_on) | DateField / date | 아니오 / True | 없음 | — |
| nonconformity_reference (nonconformity_reference) | TextField / text | 예 / True | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_supplierrecord_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_supplierrecord_tasks`, 두 필수 FK 및 쌍 unique.

N:M `capas` → `pms_capa`, 실제 중간 테이블 `pms_supplierrecord_capas`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='supplierrecord_state_valid'>
- <CheckConstraint: condition=(AND: ('supplier_type__in', ['SUPPLIER', 'SITE', 'CONTRACTOR'])) name='ra_supplierrecord_supplier_type_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 기존 BusinessPartner/CAPA 재사용. 조직 기준과 명시 기한을 적용.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `supplier_type` 허용값: SUPPLIER, SITE, CONTRACTOR

## SupplierMaterial — `pms_suppliermaterial`

공급자 문서 버전·유효기간·미비·변경 영향.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| supplier (supplier_id) | ForeignKey / bigint | 예 / False | 없음 | pms_supplierrecord.id / PROTECT |
| category (category) | CharField(20) / varchar(20) | 예 / False | 없음 | — |
| version (version) | CharField(80) / varchar(80) | 예 / False | 없음 | — |
| issued_on (issued_on) | DateField / date | 아니오 / True | 없음 | — |
| expires_on (expires_on) | DateField / date | 아니오 / True | 없음 | — |
| deficiencies (deficiencies) | TextField / text | 예 / True | 없음 | — |
| next_review_on (next_review_on) | DateField / date | 아니오 / True | 없음 | — |
| change_notice (change_notice) | TextField / text | 예 / True | 없음 | — |
| impact_review (impact_review) | TextField / text | 예 / True | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_suppliermaterial_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_suppliermaterial_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='suppliermaterial_state_valid'>
- <UniqueConstraint: fields=('supplier', 'category', 'version') name='unique_supplier_material'>
- <CheckConstraint: condition=(OR: ('expires_on__isnull', True), ('issued_on__isnull', True), ('expires_on__gte', F(issued_on))) name='supplier_material_date_order'>
- <CheckConstraint: condition=(AND: ('category__in', ['CERTIFICATE', 'CONTRACT', 'QUALITY_AGREEMENT', 'OTHER'])) name='ra_suppliermaterial_category_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 자료 원본 증빙을 승인에 요구. 만료·재검토 일수 자동 생성 없음.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `category` 허용값: CERTIFICATE, CONTRACT, QUALITY_AGREEMENT, OTHER

## TrainingRequirement — `pms_trainingrequirement`

시행 문서 버전별 역할 교육과 명시적 승인 제한.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| document (document_id) | ForeignKey / bigint | 예 / False | 없음 | pms_controlleddocument.id / PROTECT |
| required_role (required_role) | CharField(10) / varchar(10) | 예 / False | 없음 | — |
| due_on (due_on) | DateField / date | 아니오 / True | 없음 | — |
| effectiveness_method (effectiveness_method) | TextField / text | 예 / False | 없음 | — |
| enforce_ra_approval (enforce_ra_approval) | BooleanField / bool | 예 / False | False | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_trainingrequirement_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_trainingrequirement_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='trainingrequirement_state_valid'>
- <UniqueConstraint: fields=('profile', 'document', 'required_role') name='unique_role_document_training'>
- <CheckConstraint: condition=(AND: ('required_role__in', ['STAFF', 'RA_QA', 'ADMIN'])) name='ra_trainingrequiremen_required_role_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 시행 문서·역할. 승인 제한은 명시적으로 켠 신규 RA 승인에만 적용.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `required_role` 허용값: STAFF, RA_QA, ADMIN

## TrainingAssignment — `pms_trainingassignment`

대상자별 교육 시도·수료 증빙·효과 판단.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| attempt (attempt) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| requirement (requirement_id) | ForeignKey / bigint | 예 / False | 없음 | pms_trainingrequirement.id / PROTECT |
| trainee (trainee_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| due_on (due_on) | DateField / date | 아니오 / True | 없음 | — |
| completed_on (completed_on) | DateField / date | 아니오 / True | 없음 | — |
| completion_evidence (completion_evidence_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_attachment.id / PROTECT |
| training_status (training_status) | CharField(20) / varchar(20) | 예 / False | 'PENDING' | — |
| effectiveness (effectiveness) | CharField(12) / varchar(12) | 예 / False | 'UNVERIFIED' | — |
| effectiveness_rationale (effectiveness_rationale) | TextField / text | 예 / True | 없음 | — |
| retraining_of (retraining_of_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_trainingassignment.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_trainingassignment_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_trainingassignment_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision, attempt
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='trainingassignment_state_valid'>
- <CheckConstraint: condition=(AND: ('attempt__gte', 1)) name='training_positive_attempt'>
- <UniqueConstraint: fields=('requirement', 'trainee', 'attempt') name='unique_training_assignment'>
- <CheckConstraint: condition=(OR: (NOT (AND: ('training_status', 'COMPLETED'))), (AND: ('completed_on__isnull', False), ('completion_evidence__isnull', False), ('effectiveness', 'PASS'))) name='training_completion_evidence'>
- <CheckConstraint: condition=(AND: ('training_status__in', ['PENDING', 'COMPLETED', 'RETRAIN', 'NEEDS_REVIEW', 'INACTIVE'])) name='ra_trainingassignment_training_status_valid'>
- <CheckConstraint: condition=(AND: ('effectiveness__in', ['UNVERIFIED', 'PASS', 'FAIL'])) name='ra_trainingassignment_effectiveness_valid'>

명시 인덱스: ra_training_due: ['trainee', 'training_status', 'due_on']

앱/서비스 조건: 수료일·검사 증빙·효과 PASS·다른 담당자 판단을 기록. 동일 기준의 재교육 시도 계보.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `training_status` 허용값: PENDING, COMPLETED, RETRAIN, NEEDS_REVIEW, INACTIVE
- `effectiveness` 허용값: UNVERIFIED, PASS, FAIL

## AuditPlan — `pms_auditplan`

업무 감사·실사 일정·범위·기준; 시스템 AuditLog와 별도.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| audit_type (audit_type) | CharField(12) / varchar(12) | 예 / False | 없음 | — |
| scheduled_on (scheduled_on) | DateField / date | 예 / False | 없음 | — |
| scope (scope) | TextField / text | 예 / False | 없음 | — |
| criteria (criteria) | TextField / text | 예 / False | 없음 | — |
| checklist (checklist) | JSONField / text | 예 / True | dict | — |
| closure_rationale (closure_rationale) | TextField / text | 예 / True | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_auditplan_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_auditplan_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='auditplan_state_valid'>
- <CheckConstraint: condition=(AND: ('audit_type__in', ['INTERNAL', 'EXTERNAL'])) name='ra_auditplan_audit_type_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 업무 감사 일정과 종결. 모든 연결 지적 종결 필요.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `audit_type` 허용값: INTERNAL, EXTERNAL

## AuditFinding — `pms_auditfinding`

관찰·지적 분류·답변·CAPA·효과 확인.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| audit (audit_id) | ForeignKey / bigint | 예 / False | 없음 | pms_auditplan.id / PROTECT |
| observation (observation) | TextField / text | 예 / False | 없음 | — |
| classification (classification) | CharField(100) / varchar(100) | 예 / False | 없음 | — |
| classification_basis (classification_basis) | TextField / text | 예 / False | 없음 | — |
| due_on (due_on) | DateField / date | 아니오 / True | 없음 | — |
| response (response) | TextField / text | 예 / True | 없음 | — |
| capa (capa_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_capa.id / PROTECT |
| effectiveness (effectiveness) | CharField(12) / varchar(12) | 예 / False | 'UNVERIFIED' | — |
| effectiveness_rationale (effectiveness_rationale) | TextField / text | 예 / True | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_auditfinding_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_auditfinding_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='auditfinding_state_valid'>
- <CheckConstraint: condition=(AND: ('effectiveness__in', ['UNVERIFIED', 'PASS', 'FAIL'])) name='ra_auditfinding_effectiveness_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 응답·효과 근거·기존 CAPA 종결을 확인하고 종결. 변경 전후 AuditLog.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `effectiveness` 허용값: UNVERIFIED, PASS, FAIL

## AuditPackage — `pms_auditpackage`

감사별 수동 제출 자료 버전과 승인 스냅샷.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| audit (audit_id) | ForeignKey / bigint | 예 / False | 없음 | pms_auditplan.id / PROTECT |
| version (version) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| description (description) | TextField / text | 예 / False | 없음 | — |
| receipt_reference (receipt_reference) | CharField(240) / varchar(240) | 예 / True | 없음 | — |
| frozen_snapshot (frozen_snapshot) | JSONField / text | 예 / True | dict | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_auditpackage_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_auditpackage_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision, version
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='auditpackage_state_valid'>
- <UniqueConstraint: fields=('audit', 'version') name='unique_audit_package'>
- <CheckConstraint: condition=(AND: ('version__gte', 1)) name='auditpackage_positive_version'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 감사 범위 일치와 버전별 승인 파일 목록 보존, 외부 전송 없음.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## ManagementReview — `pms_managementreview`

기간 보고 건수와 캡처 시점 RA/PMS 현황 스냅샷.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| period_start (period_start) | DateField / date | 예 / False | 없음 | — |
| period_end (period_end) | DateField / date | 예 / False | 없음 | — |
| meeting_on (meeting_on) | DateField / date | 아니오 / True | 없음 | — |
| unresolved_risks (unresolved_risks) | TextField / text | 예 / True | 없음 | — |
| meeting_notes (meeting_notes) | TextField / text | 예 / True | 없음 | — |
| management_snapshot (management_snapshot) | JSONField / text | 예 / True | dict | — |
| captured_at (captured_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| pms_report (pms_report_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_reportartifact.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_managementreview_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_managementreview_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='managementreview_state_valid'>
- <CheckConstraint: condition=(AND: ('period_end__gte', F(period_start))) name='management_period_order'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 현재 캡처 상태와 기간 신규 보고 수 비교. 발생률 미산정·과거 상태 복원 없음.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## ManagementDecision — `pms_managementdecision`

경영 검토 결정·담당·후속 기한 및 결과.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| review (review_id) | ForeignKey / bigint | 예 / False | 없음 | pms_managementreview.id / PROTECT |
| decision (decision) | TextField / text | 예 / False | 없음 | — |
| rationale (rationale) | TextField / text | 예 / False | 없음 | — |
| due_on (due_on) | DateField / date | 아니오 / True | 없음 | — |
| completed_on (completed_on) | DateField / date | 아니오 / True | 없음 | — |
| outcome (outcome) | TextField / text | 예 / True | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_managementdecision_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_managementdecision_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='managementdecision_state_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 실제 후속 결과·연결 업무 완료 후 종결.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## RetentionPolicy — `pms_retentionpolicy`

조직의 근거 기반 보존·파기 검토 설정; 자동 삭제 없음.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| organization (organization_id) | ForeignKey / bigint | 예 / False | 없음 | pms_businesspartner.id / PROTECT |
| record_category (record_category) | CharField(100) / varchar(100) | 예 / False | 없음 | — |
| legal_source (legal_source_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_regulationdocument.id / PROTECT |
| source_url (source_url) | CharField(1000) / varchar(1000) | 예 / True | 없음 | — |
| checked_on (checked_on) | DateField / date | 아니오 / True | 없음 | — |
| retention_basis (retention_basis) | TextField / text | 예 / False | 없음 | — |
| duration_days (duration_days) | PositiveIntegerField / integer unsigned | 아니오 / True | 없음 | — |
| disposal_procedure (disposal_procedure) | TextField / text | 예 / True | 없음 | — |
| automatic_deletion (automatic_deletion) | BooleanField / bool | 예 / False | False | — |

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision, duration_days
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='retentionpolicy_state_valid'>
- <CheckConstraint: condition=(AND: ('automatic_deletion', False)) name='ra_no_automatic_deletion'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 조직별 근거와 기간. 자동 삭제는 DB CHECK로 항상 비활성.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## QualityDocument — `pms_qualitydocument`

시행 통제 문서의 품질매뉴얼·절차·지침·양식 계층 및 템플릿 정의.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| document (document_id) | ForeignKey / bigint | 예 / False | 없음 | pms_controlleddocument.id / PROTECT |
| parent (parent_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_qualitydocument.id / PROTECT |
| department (department) | CharField(120) / varchar(120) | 예 / False | 없음 | — |
| level (level) | CharField(12) / varchar(12) | 예 / False | 없음 | — |
| training (training_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_trainingrequirement.id / PROTECT |
| required_fields (required_fields) | JSONField / text | 예 / True | list | — |
| template_approved (template_approved) | BooleanField / bool | 예 / False | False | — |
| template_source (template_source_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_controlleddocument.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_qualitydocument_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_qualitydocument_tasks`, 두 필수 FK 및 쌍 unique.

N:M `requirements` → `pms_rarequirement`, 실제 중간 테이블 `pms_qualitydocument_requirements`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='qualitydocument_state_valid'>
- <UniqueConstraint: fields=('document',) name='one_quality_document_version'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 통제 문서 버전당 하나의 계층 정의. 상위 문서 수준과 프로필 검사. 승인된 템플릿에서 초안 생성.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `level` 허용값: MANUAL, PROCEDURE, INSTRUCTION, FORM

## QualityRecord — `pms_qualityrecord`

정확한 양식 버전의 입력 값·기한과 원기록 정정 연결.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| form_version (form_version_id) | ForeignKey / bigint | 예 / False | 없음 | pms_qualitydocument.id / PROTECT |
| project (project_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_dhfproject.id / PROTECT |
| lot (lot_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_productlot.id / PROTECT |
| change (change_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_productchange.id / PROTECT |
| training (training_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_trainingassignment.id / PROTECT |
| capa (capa_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_capa.id / PROTECT |
| due_on (due_on) | DateField / date | 아니오 / True | 없음 | — |
| record_key (record_key) | CharField(100) / varchar(100) | 예 / False | 없음 | — |
| values (values) | JSONField / text | 예 / True | dict | — |
| corrects (corrects_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_qualityrecord.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_qualityrecord_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_qualityrecord_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='qualityrecord_state_valid'>
- <UniqueConstraint: fields=('profile', 'record_key') name='unique_quality_record_key'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 신규 작성은 시행 양식만 허용. 필수 값 누락 차단. 승인된 원기록 정정은 원래 양식과 별도 행에 기록.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## QualityValidation — `pms_qualityvalidation`

품질경영용 시스템 버전의 영향·밸리데이션 계획·보고·재검토.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| system_version (system_version) | CharField(100) / varchar(100) | 예 / False | 없음 | — |
| intended_use (intended_use) | TextField / text | 예 / False | 없음 | — |
| quality_impact (quality_impact) | TextField / text | 예 / False | 없음 | — |
| plan (plan) | TextField / text | 예 / False | 없음 | — |
| acceptance (acceptance) | TextField / text | 예 / False | 없음 | — |
| report (report) | TextField / text | 예 / True | 없음 | — |
| supplier_material (supplier_material_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_suppliermaterial.id / PROTECT |
| internal_confirmation (internal_confirmation) | TextField / text | 예 / True | 없음 | — |
| previous (previous_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_qualityvalidation.id / PROTECT |
| revalidation_reason (revalidation_reason) | TextField / text | 예 / True | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_qualityvalidation_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_qualityvalidation_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='qualityvalidation_state_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 최신 시험 버전의 실행·증빙·승인 또는 사유가 있는 승인 면제 검증. 승인 당시 요구사항 추적 보존.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## ValidationRequirement — `pms_validationrequirement`

품질시스템 사용자 요구사항과 위험·통제.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| validation (validation_id) | ForeignKey / bigint | 예 / False | 없음 | pms_qualityvalidation.id / PROTECT |
| requirement (requirement) | TextField / text | 예 / False | 없음 | — |
| risk (risk) | TextField / text | 예 / False | 없음 | — |
| control (control) | TextField / text | 예 / False | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_validationrequirement_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_validationrequirement_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='validationrequirement_state_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## ValidationCase — `pms_validationcase`

승인 및 실행에 고정된 시험 케이스 버전.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| requirement (requirement_id) | ForeignKey / bigint | 예 / False | 없음 | pms_validationrequirement.id / PROTECT |
| version (version) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| procedure (procedure) | TextField / text | 예 / False | 없음 | — |
| expected (expected) | TextField / text | 예 / False | 없음 | — |
| previous (previous_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_validationcase.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_validationcase_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_validationcase_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision, version
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='validationcase_state_valid'>
- <UniqueConstraint: fields=('requirement', 'version') name='unique_validation_case_version'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 요구사항별 버전 고유. 승인된 케이스에 실행 FK 고정.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## ValidationRun — `pms_validationrun`

실행 결과·일탈·면제·재시험과 검사된 증빙.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| case (case_id) | ForeignKey / bigint | 예 / False | 없음 | pms_validationcase.id / PROTECT |
| outcome (outcome) | CharField(8) / varchar(8) | 예 / False | 없음 | — |
| result (result) | TextField / text | 예 / False | 없음 | — |
| deviation (deviation) | TextField / text | 예 / True | 없음 | — |
| retest_of (retest_of_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_validationrun.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_validationrun_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_validationrun_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='validationrun_state_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 결과·케이스·일탈 변경 차단. 재시험은 새 실행. 면제 사유와 분리 승인.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `outcome` 허용값: PASS, FAIL, WAIVED

## DHFProject — `pms_dhfproject`

규제 프로필의 제품 출시 버전별 설계 프로젝트.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| release (release_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productrevision.id / PROTECT |
| purpose (purpose) | TextField / text | 예 / False | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_dhfproject_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_dhfproject_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='dhfproject_state_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## DesignTrace — `pms_designtrace`

요구사항·설계 출력·제품 위험·검증 문서·변경·출시 연결.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| project (project_id) | ForeignKey / bigint | 예 / False | 없음 | pms_dhfproject.id / PROTECT |
| requirement (requirement_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_rarequirement.id / PROTECT |
| output (output_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_controlleddocument.id / PROTECT |
| risk (risk_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_productrisk.id / PROTECT |
| verification (verification_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_controlleddocument.id / PROTECT |
| change (change_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_productchange.id / PROTECT |
| release_review (release_review_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_productrevision.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_designtrace_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_designtrace_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='designtrace_state_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 같은 프로필의 문서·위험·변경 및 동일 출시 버전 연결. 구버전 표시.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## MeetingSource — `pms_meetingsource`

검사된 회의록 파일과 프로젝트.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| project (project_id) | ForeignKey / bigint | 예 / False | 없음 | pms_dhfproject.id / PROTECT |
| minutes (minutes_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / PROTECT |
| meeting_on (meeting_on) | DateField / date | 예 / False | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_meetingsource_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_meetingsource_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='meetingsource_state_valid'>
- <UniqueConstraint: fields=('project', 'minutes') name='unique_dhf_meeting_source'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 검사 통과 UTF-8 회의록. 프로젝트·첨부 unique. 같은 해시의 원본 중복 추출 차단.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## MeetingCandidate — `pms_meetingcandidate`

원문 위치·발췌·문서/파일 후보와 확인한 추적 행.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| meeting (meeting_id) | ForeignKey / bigint | 예 / False | 없음 | pms_meetingsource.id / PROTECT |
| line_number (line_number) | PositiveIntegerField / integer unsigned | 예 / False | 없음 | — |
| excerpt (excerpt) | TextField / text | 예 / False | 없음 | — |
| category (category) | CharField(40) / varchar(40) | 예 / False | 없음 | — |
| document (document_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_controlleddocument.id / PROTECT |
| mentioned_file (mentioned_file_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_attachment.id / PROTECT |
| suggested_owner (suggested_owner) | CharField(150) / varchar(150) | 예 / True | 없음 | — |
| suggested_due (suggested_due) | CharField(30) / varchar(30) | 예 / True | 없음 | — |
| uncertainty (uncertainty) | TextField / text | 예 / True | 없음 | — |
| confirmed_trace (confirmed_trace_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_designtrace.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_meetingcandidate_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_meetingcandidate_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision, line_number
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='meetingcandidate_state_valid'>
- <UniqueConstraint: fields=('meeting', 'line_number') name='unique_meeting_candidate_line'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 원문 행·발췌 보존. 승인 후보만 연결. 원본 행별 unique 및 확인 재요청 중복 방지.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## DHFBaseline — `pms_dhfbaseline`

DHF 기준 시점의 연결·검토 스냅샷.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| project (project_id) | ForeignKey / bigint | 예 / False | 없음 | pms_dhfproject.id / PROTECT |
| baseline (baseline) | JSONField / text | 예 / True | dict | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_dhfbaseline_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_dhfbaseline_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='dhfbaseline_state_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 캡처 시점·연결·검토 상태를 저장하고 승인. CSV/PDF 내보내기.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## SoftwareChangeReview — `pms_softwarechangereview`

담당자 변경 분류와 기능·알고리즘·사용 목적 비교.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| change (change_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productchange.id / PROTECT |
| project (project_id) | ForeignKey / bigint | 예 / False | 없음 | pms_dhfproject.id / PROTECT |
| classification (classification) | CharField(120) / varchar(120) | 예 / False | '확인 필요' | — |
| classification_basis (classification_basis) | TextField / text | 예 / True | 없음 | — |
| function_comparison (function_comparison) | TextField / text | 예 / False | 없음 | — |
| algorithm_comparison (algorithm_comparison) | TextField / text | 예 / False | 없음 | — |
| intended_use_comparison (intended_use_comparison) | TextField / text | 예 / False | 없음 | — |
| package (package_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_submissionpackage.id / PROTECT |
| submission_manifest (submission_manifest) | JSONField / text | 예 / True | dict | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_softwarechangereview_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_softwarechangereview_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='softwarechangereview_state_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 담당자 분류·근거, 준비된 시행 문서 및 동일 변경/출시 승인 패키지 요구. 제출 목록과 해시 보존.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## TechnicalSection — `pms_technicalsection`

기술문서 목차별 준비 상태·담당자·증빙.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| review (review_id) | ForeignKey / bigint | 예 / False | 없음 | pms_softwarechangereview.id / PROTECT |
| section (section) | CharField(120) / varchar(120) | 예 / False | 없음 | — |
| document (document_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_controlleddocument.id / PROTECT |
| readiness (readiness) | CharField(12) / varchar(12) | 예 / False | 'MISSING' | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_technicalsection_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_technicalsection_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='technicalsection_state_valid'>
- <UniqueConstraint: fields=('review', 'section') name='unique_review_section'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 변경심사별 목차 고유. 동일 프로필 문서·증빙 연결.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED
- `readiness` 허용값: MISSING, DRAFT, READY

## ReviewResponse — `pms_reviewresponse`

심사 질의·답변·이전 답변과 수동 제출 패키지.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| review (review_id) | ForeignKey / bigint | 예 / False | 없음 | pms_softwarechangereview.id / PROTECT |
| question (question) | TextField / text | 예 / False | 없음 | — |
| response (response) | TextField / text | 예 / True | 없음 | — |
| package (package_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_submissionpackage.id / PROTECT |
| previous (previous_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_reviewresponse.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_reviewresponse_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_reviewresponse_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='reviewresponse_state_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## SecurityInventory — `pms_securityinventory`

출시 버전의 자산·외부 인터페이스·수동 SBOM 목록.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| release (release_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productrevision.id / PROTECT |
| sbom (sbom_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_attachment.id / PROTECT |
| assets (assets) | TextField / text | 예 / True | 없음 | — |
| interfaces (interfaces) | TextField / text | 예 / True | 없음 | — |
| components (components) | JSONField / text | 예 / True | list | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_securityinventory_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_securityinventory_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='securityinventory_state_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 검사된 로컬 CSV 가져오기. 보안 적합성 판정 없음.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## SecurityFinding — `pms_securityfinding`

출처·확인일·영향·조치·잔여위험 근거.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| inventory (inventory_id) | ForeignKey / bigint | 예 / False | 없음 | pms_securityinventory.id / PROTECT |
| identifier (identifier) | CharField(120) / varchar(120) | 예 / False | 없음 | — |
| source (source) | CharField(500) / varchar(500) | 예 / False | 없음 | — |
| checked_on (checked_on) | DateField / date | 예 / False | 없음 | — |
| threat (threat) | TextField / text | 예 / False | 없음 | — |
| impact (impact) | TextField / text | 예 / False | 없음 | — |
| assessment (assessment) | TextField / text | 예 / False | 없음 | — |
| score_source_version (score_source_version) | CharField(200) / varchar(200) | 예 / True | 없음 | — |
| score_as_reported (score_as_reported) | CharField(80) / varchar(80) | 예 / True | 없음 | — |
| due_on (due_on) | DateField / date | 아니오 / True | 없음 | — |
| patch (patch) | TextField / text | 예 / True | 없음 | — |
| residual (residual) | TextField / text | 예 / True | 없음 | — |
| risk (risk_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_productrisk.id / PROTECT |
| change (change_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_productchange.id / PROTECT |
| capa (capa_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_capa.id / PROTECT |
| action (action_id) | ForeignKey / bigint | 아니오 / True | 없음 | pms_fieldsafetyaction.id / PROTECT |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_securityfinding_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_securityfinding_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='securityfinding_state_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 수동 점수 출처·버전과 확인일. 제품 범위 검사. 조치 검증 증빙과 잔여위험 판단.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## SecurityReview — `pms_securityreview`

출시 버전 보안 시험·증빙·미해결 항목·담당자 승인.

민감도: 민감 자료 포함; 본문·JSON·파일 접근 제한 필요.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| title (title) | CharField(240) / varchar(240) | 예 / False | 없음 | — |
| owner (owner_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewer (reviewer_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| created_by (created_by_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / PROTECT |
| reviewed_by (reviewed_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| reviewed_at (reviewed_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approved_by (approved_by_id) | ForeignKey / integer | 아니오 / True | 없음 | auth_user.id / PROTECT |
| approved_at (approved_at) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| approval_snapshot (approval_snapshot) | JSONField / text | 예 / True | dict | — |
| state (state) | CharField(12) / varchar(12) | 예 / False | 'DRAFT' | — |
| revision (revision) | PositiveIntegerField / integer unsigned | 예 / False | 1 | — |
| is_example (is_example) | BooleanField / bool | 예 / False | False | — |
| created_at (created_at) | DateTimeField / datetime | 예 / True | 생성 시 now | — |
| updated_at (updated_at) | DateTimeField / datetime | 예 / True | 저장 시 now | — |
| profile (profile_id) | ForeignKey / bigint | 예 / False | 없음 | pms_regulatoryprofile.id / PROTECT |
| inventory (inventory_id) | ForeignKey / bigint | 예 / False | 없음 | pms_securityinventory.id / PROTECT |
| test_plan (test_plan) | TextField / text | 예 / False | 없음 | — |
| test_results (test_results) | TextField / text | 예 / True | 없음 | — |
| open_items (open_items) | TextField / text | 예 / True | 없음 | — |
| residual_decision (residual_decision) | TextField / text | 예 / True | 없음 | — |

N:M `evidence` → `pms_attachment`, 실제 중간 테이블 `pms_securityreview_evidence`, 두 필수 FK 및 쌍 unique.

N:M `tasks` → `pms_worktask`, 실제 중간 테이블 `pms_securityreview_tasks`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id
- unique_together: ()
- 타입의 암묵적 DB 비음수 CHECK: revision
- <CheckConstraint: condition=(AND: ('state__in', ['DRAFT', 'REVIEW', 'REVIEWED', 'APPROVED', 'EFFECTIVE', 'RETIRED', 'CANCELLED', 'CLOSED'])) name='securityreview_state_valid'>

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 구성 목록·시험 결과·증빙·잔여위험 담당자 검토. 미해결 항목 조치 기록.
- `state` 허용값: DRAFT, REVIEW, REVIEWED, APPROVED, EFFECTIVE, RETIRED, CANCELLED, CLOSED

## User — `auth_user`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | AutoField / integer | 예 / True | DB 자동 증가 | — |
| password (password) | CharField(128) / varchar(128) | 예 / False | 없음 | — |
| last_login (last_login) | DateTimeField / datetime | 아니오 / True | 없음 | — |
| is_superuser (is_superuser) | BooleanField / bool | 예 / False | False | — |
| username (username) | CharField(150) / varchar(150) | 예 / False | 없음 | — |
| first_name (first_name) | CharField(150) / varchar(150) | 예 / True | 없음 | — |
| last_name (last_name) | CharField(150) / varchar(150) | 예 / True | 없음 | — |
| email (email) | CharField(254) / varchar(254) | 예 / True | 없음 | — |
| is_staff (is_staff) | BooleanField / bool | 예 / False | False | — |
| is_active (is_active) | BooleanField / bool | 예 / False | True | — |
| date_joined (date_joined) | DateTimeField / datetime | 예 / False | now | — |

N:M `groups` → `auth_group`, 실제 중간 테이블 `auth_user_groups`, 두 필수 FK 및 쌍 unique.

N:M `user_permissions` → `auth_permission`, 실제 중간 테이블 `auth_user_user_permissions`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id, username
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## Group — `auth_group`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | AutoField / integer | 예 / True | DB 자동 증가 | — |
| name (name) | CharField(150) / varchar(150) | 예 / False | 없음 | — |

N:M `permissions` → `auth_permission`, 실제 중간 테이블 `auth_group_permissions`, 두 필수 FK 및 쌍 unique.

DB 제약:

- PK/필드 unique: id, name
- unique_together: ()

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## Permission — `auth_permission`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | AutoField / integer | 예 / True | DB 자동 증가 | — |
| name (name) | CharField(255) / varchar(255) | 예 / False | 없음 | — |
| content_type (content_type_id) | ForeignKey / integer | 예 / False | 없음 | django_content_type.id / CASCADE |
| codename (codename) | CharField(100) / varchar(100) | 예 / False | 없음 | — |

DB 제약:

- PK/필드 unique: id
- unique_together: (('content_type', 'codename'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## CAPAEvaluation_evidence — `pms_capaevaluation_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| capaevaluation (capaevaluation_id) | ForeignKey / bigint | 예 / False | 없음 | pms_capaevaluation.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('capaevaluation', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## RARequirement_evidence — `pms_rarequirement_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| rarequirement (rarequirement_id) | ForeignKey / bigint | 예 / False | 없음 | pms_rarequirement.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('rarequirement', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## RARequirement_tasks — `pms_rarequirement_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| rarequirement (rarequirement_id) | ForeignKey / bigint | 예 / False | 없음 | pms_rarequirement.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('rarequirement', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## MarketingAuthorization_evidence — `pms_marketingauthorization_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| marketingauthorization (marketingauthorization_id) | ForeignKey / bigint | 예 / False | 없음 | pms_marketingauthorization.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('marketingauthorization', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## MarketingAuthorization_tasks — `pms_marketingauthorization_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| marketingauthorization (marketingauthorization_id) | ForeignKey / bigint | 예 / False | 없음 | pms_marketingauthorization.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('marketingauthorization', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SubmissionPackage_evidence — `pms_submissionpackage_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| submissionpackage (submissionpackage_id) | ForeignKey / bigint | 예 / False | 없음 | pms_submissionpackage.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('submissionpackage', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SubmissionPackage_tasks — `pms_submissionpackage_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| submissionpackage (submissionpackage_id) | ForeignKey / bigint | 예 / False | 없음 | pms_submissionpackage.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('submissionpackage', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ProductRevision_evidence — `pms_productrevision_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| productrevision (productrevision_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productrevision.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('productrevision', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ProductRevision_tasks — `pms_productrevision_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| productrevision (productrevision_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productrevision.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('productrevision', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ControlledDocument_evidence — `pms_controlleddocument_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| controlleddocument (controlleddocument_id) | ForeignKey / bigint | 예 / False | 없음 | pms_controlleddocument.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('controlleddocument', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ControlledDocument_tasks — `pms_controlleddocument_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| controlleddocument (controlleddocument_id) | ForeignKey / bigint | 예 / False | 없음 | pms_controlleddocument.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('controlleddocument', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ProductChange_evidence — `pms_productchange_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| productchange (productchange_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productchange.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('productchange', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ProductChange_tasks — `pms_productchange_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| productchange (productchange_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productchange.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('productchange', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ProductChange_lots — `pms_productchange_lots`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| productchange (productchange_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productchange.id / CASCADE |
| productlot (productlot_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productlot.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('productchange', 'productlot'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ProductChange_documents — `pms_productchange_documents`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| productchange (productchange_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productchange.id / CASCADE |
| controlleddocument (controlleddocument_id) | ForeignKey / bigint | 예 / False | 없음 | pms_controlleddocument.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('productchange', 'controlleddocument'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## LabelVersion_evidence — `pms_labelversion_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| labelversion (labelversion_id) | ForeignKey / bigint | 예 / False | 없음 | pms_labelversion.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('labelversion', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## LabelVersion_tasks — `pms_labelversion_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| labelversion (labelversion_id) | ForeignKey / bigint | 예 / False | 없음 | pms_labelversion.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('labelversion', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## LabelVersion_lots — `pms_labelversion_lots`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| labelversion (labelversion_id) | ForeignKey / bigint | 예 / False | 없음 | pms_labelversion.id / CASCADE |
| productlot (productlot_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productlot.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('labelversion', 'productlot'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## RiskCriteria_evidence — `pms_riskcriteria_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| riskcriteria (riskcriteria_id) | ForeignKey / bigint | 예 / False | 없음 | pms_riskcriteria.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('riskcriteria', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## RiskCriteria_tasks — `pms_riskcriteria_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| riskcriteria (riskcriteria_id) | ForeignKey / bigint | 예 / False | 없음 | pms_riskcriteria.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('riskcriteria', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ProductRisk_evidence — `pms_productrisk_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| productrisk (productrisk_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productrisk.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('productrisk', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ProductRisk_tasks — `pms_productrisk_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| productrisk (productrisk_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productrisk.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('productrisk', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ProductRisk_complaints — `pms_productrisk_complaints`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| productrisk (productrisk_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productrisk.id / CASCADE |
| customercomplaint (customercomplaint_id) | ForeignKey / bigint | 예 / False | 없음 | pms_customercomplaint.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('productrisk', 'customercomplaint'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ProductRisk_adverse_events — `pms_productrisk_adverse_events`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| productrisk (productrisk_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productrisk.id / CASCADE |
| adverseevent (adverseevent_id) | ForeignKey / bigint | 예 / False | 없음 | pms_adverseevent.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('productrisk', 'adverseevent'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ProductRisk_signals — `pms_productrisk_signals`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| productrisk (productrisk_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productrisk.id / CASCADE |
| safetysignal (safetysignal_id) | ForeignKey / bigint | 예 / False | 없음 | pms_safetysignal.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('productrisk', 'safetysignal'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ProductRisk_capas — `pms_productrisk_capas`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| productrisk (productrisk_id) | ForeignKey / bigint | 예 / False | 없음 | pms_productrisk.id / CASCADE |
| capa (capa_id) | ForeignKey / bigint | 예 / False | 없음 | pms_capa.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('productrisk', 'capa'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SafetyInformation_evidence — `pms_safetyinformation_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| safetyinformation (safetyinformation_id) | ForeignKey / bigint | 예 / False | 없음 | pms_safetyinformation.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('safetyinformation', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SafetyInformation_tasks — `pms_safetyinformation_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| safetyinformation (safetyinformation_id) | ForeignKey / bigint | 예 / False | 없음 | pms_safetyinformation.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('safetyinformation', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## FieldSafetyAction_evidence — `pms_fieldsafetyaction_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| fieldsafetyaction (fieldsafetyaction_id) | ForeignKey / bigint | 예 / False | 없음 | pms_fieldsafetyaction.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('fieldsafetyaction', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## FieldSafetyAction_tasks — `pms_fieldsafetyaction_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| fieldsafetyaction (fieldsafetyaction_id) | ForeignKey / bigint | 예 / False | 없음 | pms_fieldsafetyaction.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('fieldsafetyaction', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## FieldActionRecipient_evidence — `pms_fieldactionrecipient_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| fieldactionrecipient (fieldactionrecipient_id) | ForeignKey / bigint | 예 / False | 없음 | pms_fieldactionrecipient.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('fieldactionrecipient', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## FieldActionRecipient_tasks — `pms_fieldactionrecipient_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| fieldactionrecipient (fieldactionrecipient_id) | ForeignKey / bigint | 예 / False | 없음 | pms_fieldactionrecipient.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('fieldactionrecipient', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SupplierRecord_evidence — `pms_supplierrecord_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| supplierrecord (supplierrecord_id) | ForeignKey / bigint | 예 / False | 없음 | pms_supplierrecord.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('supplierrecord', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SupplierRecord_tasks — `pms_supplierrecord_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| supplierrecord (supplierrecord_id) | ForeignKey / bigint | 예 / False | 없음 | pms_supplierrecord.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('supplierrecord', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SupplierRecord_capas — `pms_supplierrecord_capas`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| supplierrecord (supplierrecord_id) | ForeignKey / bigint | 예 / False | 없음 | pms_supplierrecord.id / CASCADE |
| capa (capa_id) | ForeignKey / bigint | 예 / False | 없음 | pms_capa.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('supplierrecord', 'capa'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SupplierMaterial_evidence — `pms_suppliermaterial_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| suppliermaterial (suppliermaterial_id) | ForeignKey / bigint | 예 / False | 없음 | pms_suppliermaterial.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('suppliermaterial', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SupplierMaterial_tasks — `pms_suppliermaterial_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| suppliermaterial (suppliermaterial_id) | ForeignKey / bigint | 예 / False | 없음 | pms_suppliermaterial.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('suppliermaterial', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## TrainingRequirement_evidence — `pms_trainingrequirement_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| trainingrequirement (trainingrequirement_id) | ForeignKey / bigint | 예 / False | 없음 | pms_trainingrequirement.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('trainingrequirement', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## TrainingRequirement_tasks — `pms_trainingrequirement_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| trainingrequirement (trainingrequirement_id) | ForeignKey / bigint | 예 / False | 없음 | pms_trainingrequirement.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('trainingrequirement', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## TrainingAssignment_evidence — `pms_trainingassignment_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| trainingassignment (trainingassignment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_trainingassignment.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('trainingassignment', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## TrainingAssignment_tasks — `pms_trainingassignment_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| trainingassignment (trainingassignment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_trainingassignment.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('trainingassignment', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## AuditPlan_evidence — `pms_auditplan_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| auditplan (auditplan_id) | ForeignKey / bigint | 예 / False | 없음 | pms_auditplan.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('auditplan', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## AuditPlan_tasks — `pms_auditplan_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| auditplan (auditplan_id) | ForeignKey / bigint | 예 / False | 없음 | pms_auditplan.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('auditplan', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## AuditFinding_evidence — `pms_auditfinding_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| auditfinding (auditfinding_id) | ForeignKey / bigint | 예 / False | 없음 | pms_auditfinding.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('auditfinding', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## AuditFinding_tasks — `pms_auditfinding_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| auditfinding (auditfinding_id) | ForeignKey / bigint | 예 / False | 없음 | pms_auditfinding.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('auditfinding', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## AuditPackage_evidence — `pms_auditpackage_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| auditpackage (auditpackage_id) | ForeignKey / bigint | 예 / False | 없음 | pms_auditpackage.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('auditpackage', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## AuditPackage_tasks — `pms_auditpackage_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| auditpackage (auditpackage_id) | ForeignKey / bigint | 예 / False | 없음 | pms_auditpackage.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('auditpackage', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ManagementReview_evidence — `pms_managementreview_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| managementreview (managementreview_id) | ForeignKey / bigint | 예 / False | 없음 | pms_managementreview.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('managementreview', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ManagementReview_tasks — `pms_managementreview_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| managementreview (managementreview_id) | ForeignKey / bigint | 예 / False | 없음 | pms_managementreview.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('managementreview', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ManagementDecision_evidence — `pms_managementdecision_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| managementdecision (managementdecision_id) | ForeignKey / bigint | 예 / False | 없음 | pms_managementdecision.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('managementdecision', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ManagementDecision_tasks — `pms_managementdecision_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| managementdecision (managementdecision_id) | ForeignKey / bigint | 예 / False | 없음 | pms_managementdecision.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('managementdecision', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## QualityDocument_evidence — `pms_qualitydocument_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| qualitydocument (qualitydocument_id) | ForeignKey / bigint | 예 / False | 없음 | pms_qualitydocument.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('qualitydocument', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## QualityDocument_tasks — `pms_qualitydocument_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| qualitydocument (qualitydocument_id) | ForeignKey / bigint | 예 / False | 없음 | pms_qualitydocument.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('qualitydocument', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## QualityDocument_requirements — `pms_qualitydocument_requirements`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| qualitydocument (qualitydocument_id) | ForeignKey / bigint | 예 / False | 없음 | pms_qualitydocument.id / CASCADE |
| rarequirement (rarequirement_id) | ForeignKey / bigint | 예 / False | 없음 | pms_rarequirement.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('qualitydocument', 'rarequirement'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## QualityRecord_evidence — `pms_qualityrecord_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| qualityrecord (qualityrecord_id) | ForeignKey / bigint | 예 / False | 없음 | pms_qualityrecord.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('qualityrecord', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## QualityRecord_tasks — `pms_qualityrecord_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| qualityrecord (qualityrecord_id) | ForeignKey / bigint | 예 / False | 없음 | pms_qualityrecord.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('qualityrecord', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## QualityValidation_evidence — `pms_qualityvalidation_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| qualityvalidation (qualityvalidation_id) | ForeignKey / bigint | 예 / False | 없음 | pms_qualityvalidation.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('qualityvalidation', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## QualityValidation_tasks — `pms_qualityvalidation_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| qualityvalidation (qualityvalidation_id) | ForeignKey / bigint | 예 / False | 없음 | pms_qualityvalidation.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('qualityvalidation', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ValidationRequirement_evidence — `pms_validationrequirement_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| validationrequirement (validationrequirement_id) | ForeignKey / bigint | 예 / False | 없음 | pms_validationrequirement.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('validationrequirement', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ValidationRequirement_tasks — `pms_validationrequirement_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| validationrequirement (validationrequirement_id) | ForeignKey / bigint | 예 / False | 없음 | pms_validationrequirement.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('validationrequirement', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ValidationCase_evidence — `pms_validationcase_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| validationcase (validationcase_id) | ForeignKey / bigint | 예 / False | 없음 | pms_validationcase.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('validationcase', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ValidationCase_tasks — `pms_validationcase_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| validationcase (validationcase_id) | ForeignKey / bigint | 예 / False | 없음 | pms_validationcase.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('validationcase', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ValidationRun_evidence — `pms_validationrun_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| validationrun (validationrun_id) | ForeignKey / bigint | 예 / False | 없음 | pms_validationrun.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('validationrun', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ValidationRun_tasks — `pms_validationrun_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| validationrun (validationrun_id) | ForeignKey / bigint | 예 / False | 없음 | pms_validationrun.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('validationrun', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## DHFProject_evidence — `pms_dhfproject_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| dhfproject (dhfproject_id) | ForeignKey / bigint | 예 / False | 없음 | pms_dhfproject.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('dhfproject', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## DHFProject_tasks — `pms_dhfproject_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| dhfproject (dhfproject_id) | ForeignKey / bigint | 예 / False | 없음 | pms_dhfproject.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('dhfproject', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## DesignTrace_evidence — `pms_designtrace_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| designtrace (designtrace_id) | ForeignKey / bigint | 예 / False | 없음 | pms_designtrace.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('designtrace', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## DesignTrace_tasks — `pms_designtrace_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| designtrace (designtrace_id) | ForeignKey / bigint | 예 / False | 없음 | pms_designtrace.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('designtrace', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## MeetingSource_evidence — `pms_meetingsource_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| meetingsource (meetingsource_id) | ForeignKey / bigint | 예 / False | 없음 | pms_meetingsource.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('meetingsource', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## MeetingSource_tasks — `pms_meetingsource_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| meetingsource (meetingsource_id) | ForeignKey / bigint | 예 / False | 없음 | pms_meetingsource.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('meetingsource', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## MeetingCandidate_evidence — `pms_meetingcandidate_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| meetingcandidate (meetingcandidate_id) | ForeignKey / bigint | 예 / False | 없음 | pms_meetingcandidate.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('meetingcandidate', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## MeetingCandidate_tasks — `pms_meetingcandidate_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| meetingcandidate (meetingcandidate_id) | ForeignKey / bigint | 예 / False | 없음 | pms_meetingcandidate.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('meetingcandidate', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## DHFBaseline_evidence — `pms_dhfbaseline_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| dhfbaseline (dhfbaseline_id) | ForeignKey / bigint | 예 / False | 없음 | pms_dhfbaseline.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('dhfbaseline', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## DHFBaseline_tasks — `pms_dhfbaseline_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| dhfbaseline (dhfbaseline_id) | ForeignKey / bigint | 예 / False | 없음 | pms_dhfbaseline.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('dhfbaseline', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SoftwareChangeReview_evidence — `pms_softwarechangereview_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| softwarechangereview (softwarechangereview_id) | ForeignKey / bigint | 예 / False | 없음 | pms_softwarechangereview.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('softwarechangereview', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SoftwareChangeReview_tasks — `pms_softwarechangereview_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| softwarechangereview (softwarechangereview_id) | ForeignKey / bigint | 예 / False | 없음 | pms_softwarechangereview.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('softwarechangereview', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## TechnicalSection_evidence — `pms_technicalsection_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| technicalsection (technicalsection_id) | ForeignKey / bigint | 예 / False | 없음 | pms_technicalsection.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('technicalsection', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## TechnicalSection_tasks — `pms_technicalsection_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| technicalsection (technicalsection_id) | ForeignKey / bigint | 예 / False | 없음 | pms_technicalsection.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('technicalsection', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ReviewResponse_evidence — `pms_reviewresponse_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| reviewresponse (reviewresponse_id) | ForeignKey / bigint | 예 / False | 없음 | pms_reviewresponse.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('reviewresponse', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## ReviewResponse_tasks — `pms_reviewresponse_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| reviewresponse (reviewresponse_id) | ForeignKey / bigint | 예 / False | 없음 | pms_reviewresponse.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('reviewresponse', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SecurityInventory_evidence — `pms_securityinventory_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| securityinventory (securityinventory_id) | ForeignKey / bigint | 예 / False | 없음 | pms_securityinventory.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('securityinventory', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SecurityInventory_tasks — `pms_securityinventory_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| securityinventory (securityinventory_id) | ForeignKey / bigint | 예 / False | 없음 | pms_securityinventory.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('securityinventory', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SecurityFinding_evidence — `pms_securityfinding_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| securityfinding (securityfinding_id) | ForeignKey / bigint | 예 / False | 없음 | pms_securityfinding.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('securityfinding', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SecurityFinding_tasks — `pms_securityfinding_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| securityfinding (securityfinding_id) | ForeignKey / bigint | 예 / False | 없음 | pms_securityfinding.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('securityfinding', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SecurityReview_evidence — `pms_securityreview_evidence`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| securityreview (securityreview_id) | ForeignKey / bigint | 예 / False | 없음 | pms_securityreview.id / CASCADE |
| attachment (attachment_id) | ForeignKey / bigint | 예 / False | 없음 | pms_attachment.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('securityreview', 'attachment'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## SecurityReview_tasks — `pms_securityreview_tasks`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | BigAutoField / integer | 예 / True | DB 자동 증가 | — |
| securityreview (securityreview_id) | ForeignKey / bigint | 예 / False | 없음 | pms_securityreview.id / CASCADE |
| worktask (worktask_id) | ForeignKey / bigint | 예 / False | 없음 | pms_worktask.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('securityreview', 'worktask'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## User_groups — `auth_user_groups`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | AutoField / integer | 예 / True | DB 자동 증가 | — |
| user (user_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / CASCADE |
| group (group_id) | ForeignKey / integer | 예 / False | 없음 | auth_group.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('user', 'group'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## User_user_permissions — `auth_user_user_permissions`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | AutoField / integer | 예 / True | DB 자동 증가 | — |
| user (user_id) | ForeignKey / integer | 예 / False | 없음 | auth_user.id / CASCADE |
| permission (permission_id) | ForeignKey / integer | 예 / False | 없음 | auth_permission.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('user', 'permission'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.

## Group_permissions — `auth_group_permissions`

Django 기본 인증·역할 권한 테이블.

민감도: 계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.

변경/보존: 현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.

| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |
|---|---|---|---|---|
| id (id) PK | AutoField / integer | 예 / True | DB 자동 증가 | — |
| group (group_id) | ForeignKey / integer | 예 / False | 없음 | auth_group.id / CASCADE |
| permission (permission_id) | ForeignKey / integer | 예 / False | 없음 | auth_permission.id / CASCADE |

DB 제약:

- PK/필드 unique: id
- unique_together: (('group', 'permission'),)

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.
