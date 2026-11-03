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
| complaint (complaint_id) | ForeignKey / bigint | 예 / False | 없음 | pms_customercomplaint.id / PROTECT |
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

명시 인덱스: 없음 (FK/unique 인덱스는 별도 존재)

앱/서비스 조건: 필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.
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
| complaint (complaint_id) | ForeignKey / bigint | 예 / False | 없음 | pms_customercomplaint.id / PROTECT |
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
- <CheckConstraint: condition=(OR: ('capa__isnull', True), ('recall__isnull', True)) name='task_one_action_parent'>
- <CheckConstraint: condition=(AND: ('status__in', ['WAITING', 'IN_PROGRESS', 'REVIEW', 'DONE'])) name='worktask_status_valid'>

명시 인덱스: pms_worktas_assigne_e0e5e2_idx: ['assignee', 'status', 'due_at']

앱/서비스 조건: 사건/조치 일치, 활성 담당자, STAFF 접수자 범위; save_task에서 권한·시각·변경 이력.
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
