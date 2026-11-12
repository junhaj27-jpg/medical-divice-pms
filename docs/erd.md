# MedWatch PMS ERD

## 도메인 개요

사건은 제품·UDI·선택 LOT를 참조하며 위험평가, 이상사례, CAPA, 보고서, 리콜 및 업무를 모은다. 규칙은 원문 청크를 인용하는 버전으로 관리하고 사건 적용은 당시 스냅샷을 남긴다. 외부 CSV 분석 레코드는 제품 문자열을 사용하며 내부 제품 FK로 자동 연결하지 않는다.

기존 구현: 아래 물리 관계 중 두 History 테이블을 제외한 모델. 이번 추가: RiskAssessmentHistory·RegulatoryReportHistory, 삭제 보호, 제약과 조회 인덱스. RA 확장: 1~4단계의 26개 기반 모델과 실무 추적 모델 17개, 기존 WorkTask·Attachment의 사건/RA 프로필 중 하나를 택하는 문맥, 프로필·국가·조직·버전·업무·증빙의 명시 관계. 각 영역의 구현 상태는 [RA 요구사항 매트릭스](ra-requirements-matrix.md) 참조. 향후 제안: 안전 신호의 JSON 증거·조치 연결을 명시적 FK 연결 테이블로 전환, 범용 승인 대상의 명시 FK 전환. 제안은 아래 ERD에 구현처럼 표시하지 않았다.

## 물리 ERD 표기

`||` 필수 1, `o|` 선택 0..1, `o{` 선택 0..N. 자식의 FK null 여부가 부모 쪽 선택성을 결정한다. OneToOne은 자식 쪽 0..1이다. 모든 자식 FK 관계의 부모는 자식을 갖지 않을 수 있다. N:M은 실제 중간 테이블의 두 1:N 관계로 표시한다. 필드는 실제 DB column이며 PK/FK/UK를 표시한다. 타입은 Django 물리 필드 타입이며 DB별 SQL 매핑은 데이터 사전에 적었다. 반복 엔터티는 같은 테이블이다.

Approval.content_type/object_id, AuditLog.object_type/object_id, SafetyReview.links, 신호 snapshot의 evidence IDs는 논리 참조이며 FK 선을 그리지 않았다. family_key도 RuleFamilyLock.key에 대한 FK가 아니다. 기존 PMS 제출 상태와 별도로 RA 인허가에는 수동 기록 SubmissionPackage 버전이 있다. 외부 자동 제출 기능은 없다.

## 해외 인허가와 시장별 검토

```mermaid
erDiagram
    USER ||--o| MARKET_ACCESS : grants
    MEDICAL_DEVICE ||--o{ PRODUCT_MARKET : registers
    MEDICAL_DEVICE ||--o{ HARMONISED_STANDARD_REVIEW : assesses
    MEDICAL_DEVICE ||--o{ FDA_510K_REVIEW : references
    USER ||--o{ HARMONISED_STANDARD_REVIEW : reviews
    USER ||--o{ FDA_510K_REVIEW : reviews
    FDA_510K_REVIEW o|--o{ FDA_510K_REVIEW : previous
    MEDICAL_DEVICE ||--o{ MARKET_EVIDENCE : scopes
    REGULATION_DOCUMENT o|--o{ MARKET_EVIDENCE : sources
    MARKET_EVIDENCE ||--o{ MARKET_TRANSLATION : translates
    CUSTOMER_COMPLAINT ||--o{ CASE_MARKET : covers
    CASE_MARKET ||--o{ MARKET_ASSESSMENT : evaluates
    REPORTING_RULE o|--o{ MARKET_ASSESSMENT : applies
    REPORTING_RULE ||--o{ MARKET_COMPARISON_RUN : baseline
    REPORTING_RULE ||--o{ MARKET_COMPARISON_RUN : proposed
    MARKET_COMPARISON_RUN ||--o{ MARKET_COMPARISON_RESULT : contains
    CASE_MARKET ||--o{ MARKET_COMPARISON_RESULT : compares
    MARKET_COMPARISON_RESULT ||--o{ MARKET_COMPARISON_REVIEW : records
    MARKET_COMPARISON_RESULT o|--o| WORK_TASK : follows_up
    USER ||--o{ MARKET_COMPARISON_REVIEW : reviews

    FDA_510K_REVIEW {
        BigAutoField id PK
        ForeignKey device_id FK
        ForeignKey previous_id FK "nullable"
        ForeignKey reviewer_id FK
        CharField purpose
        CharField k_number
        CharField fda_device_name
        CharField applicant_name
        CharField product_code
        DateField decision_date
        CharField fda_decision
        URLField fda_detail_url
        TextField review_opinion
        DateTimeField reviewed_at
    }
    HARMONISED_STANDARD_REVIEW {
        BigAutoField id PK
        ForeignKey device_id FK
        ForeignKey reviewer_id FK
        CharField regulation
        CharField standard_number
        CharField edition
        URLField eurlex_url
        DateField checked_on "nullable for older reviews"
        CharField decision_number
        CharField decision_item
        CharField applicability
        TextField applicability_reason
        DateField review_date
        DateTimeField recorded_at
    }
    MARKET_COMPARISON_RUN {
        BigAutoField id PK
        ForeignKey baseline_id FK
        ForeignKey proposed_id FK
        ForeignKey actor_id FK
        CharField market
        DateTimeField recorded_at
        JSONField rules
    }
    MARKET_COMPARISON_RESULT {
        BigAutoField id PK
        ForeignKey run_id FK
        ForeignKey entry_id FK
        JSONField snapshot
    }
    MARKET_COMPARISON_REVIEW {
        BigAutoField id PK
        ForeignKey result_id FK
        ForeignKey actor_id FK
        DateTimeField recorded_at
        BooleanField complete
        CharField note
        CharField conclusion
        JSONField evidence
        CharField correction_reason
    }
    WORK_TASK {
        BigAutoField id PK
        OneToOneField market_comparison_id FK, UK "nullable"
    }
```

- **미국 FDA 510(k)** 검토는 제품에 속하는 추가 전용 기록이다. 선택적 `previous_id`는 같은 제품의 이전 검토를 가리키며, K-number·FDA 원문 URL·내부 검토 의견 등의 차이를 보여준다. 원문 결정은 `fda_decision`, 내부 의견은 `review_opinion`에 기록한다. 미국 등록 상태와 신청 결과는 각자의 업무 모델에서 관리한다.
- **EU 조화표준**은 공식 목록 근거와 제품 적용 판단을 같은 검토 행의 별도 필드에 기록한다. 직전 검토는 같은 제품·규정·표준 번호에서 현재 행보다 앞선 최신 행을 조회한다.
- **시장별 규칙 비교**는 실행의 `rules`와 결과의 `snapshot`에 당시 값을 저장한다. 검토 결론과 정정은 별도 행으로 추가하고, 선택한 문서 정보는 `evidence` JSON에 보존한다. 후속 업무는 선택적 일대일 관계다. CSV는 저장된 비교 결과와 최신 검토 상태를 읽는다.

## 사용자·역할·제품·UDI·LOT

```mermaid
erDiagram
    auth_user {
        AutoField id PK
        CharField password
        DateTimeField last_login
        BooleanField is_superuser
        CharField username UK
        CharField first_name
        CharField last_name
        CharField email
        BooleanField is_staff
        BooleanField is_active
        DateTimeField date_joined
    }
    auth_group {
        AutoField id PK
        CharField name UK
    }
    auth_permission {
        AutoField id PK
        CharField name
        ForeignKey content_type_id FK
        CharField codename
    }
    pms_profile {
        BigAutoField id PK
        OneToOneField user_id FK,UK
        CharField role
        CharField timezone_name
    }
    pms_manufacturer {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        CharField name UK
        CharField country
        CharField contact_email
    }
    pms_medicaldevice {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey manufacturer_id FK
        CharField name
        CharField model_number
        CharField risk_class
        BooleanField active
    }
    pms_udi {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey device_id FK
        CharField device_identifier UK
    }
    pms_productlot {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey device_id FK
        ForeignKey udi_id FK
        CharField lot_number
        CharField serial_number
        DateField manufactured_on
        DateField expires_on
        PositiveIntegerField distributed_quantity
    }
    auth_user_groups {
        AutoField id PK
        ForeignKey user_id FK
        ForeignKey group_id FK
    }
    auth_user_user_permissions {
        AutoField id PK
        ForeignKey user_id FK
        ForeignKey permission_id FK
    }
    auth_group_permissions {
        AutoField id PK
        ForeignKey group_id FK
        ForeignKey permission_id FK
    }
    django_content_type {
        AutoField id PK
    }
    django_content_type ||--o{ auth_permission : "content_type_id"
    auth_user ||--o| pms_profile : "user_id"
    pms_manufacturer ||--o{ pms_medicaldevice : "manufacturer_id"
    pms_medicaldevice ||--o{ pms_udi : "device_id"
    pms_medicaldevice ||--o{ pms_productlot : "device_id"
    pms_udi ||--o{ pms_productlot : "udi_id"
    auth_user ||--o{ auth_user_groups : "user_id"
    auth_group ||--o{ auth_user_groups : "group_id"
    auth_user ||--o{ auth_user_user_permissions : "user_id"
    auth_permission ||--o{ auth_user_user_permissions : "permission_id"
    auth_group ||--o{ auth_group_permissions : "group_id"
    auth_permission ||--o{ auth_group_permissions : "permission_id"
```

## 불만·이상사례·익명 환자·위험평가

```mermaid
erDiagram
    pms_customercomplaint {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        BooleanField is_example
        ForeignKey device_id FK
        ForeignKey udi_id FK
        ForeignKey lot_id FK
        CharField serial_number
        CharField complaint_type
        CharField title
        TextField description
        DateField occurred_on
        DateField reported_on
        ForeignKey reporter_id FK
        ForeignKey assignee_id FK
        CharField status
        DateField due_date
        PositiveIntegerField version
    }
    pms_patientanonymousinfo {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        OneToOneField complaint_id FK,UK
        CharField anonymous_code UK
        CharField age_band
        CharField sex
        TextField notes
    }
    pms_adverseevent {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        OneToOneField complaint_id FK,UK
        ForeignKey patient_id FK
        CharField event_type
        CharField outcome
        BooleanField serious
        TextField narrative
    }
    pms_riskassessment {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        OneToOneField complaint_id FK,UK
        PositiveSmallIntegerField severity
        PositiveSmallIntegerField probability
        PositiveSmallIntegerField score
        CharField level
        BooleanField capa_review_required
        TextField rationale
        ForeignKey assessed_by_id FK
    }
    pms_riskassessmenthistory {
        BigAutoField id PK
        ForeignKey actor_id FK
        DateTimeField created_at
        TextField reason
        CharField source
        JSONField before
        JSONField after
        ForeignKey parent_id FK
    }
    pms_medicaldevice {
        BigAutoField id PK
    }
    pms_udi {
        BigAutoField id PK
    }
    pms_productlot {
        BigAutoField id PK
    }
    auth_user {
        AutoField id PK
    }
    pms_medicaldevice ||--o{ pms_customercomplaint : "device_id"
    pms_udi ||--o{ pms_customercomplaint : "udi_id"
    pms_productlot |o--o{ pms_customercomplaint : "lot_id"
    auth_user ||--o{ pms_customercomplaint : "reporter_id"
    auth_user |o--o{ pms_customercomplaint : "assignee_id"
    pms_customercomplaint ||--o| pms_patientanonymousinfo : "complaint_id"
    pms_customercomplaint ||--o| pms_adverseevent : "complaint_id"
    pms_patientanonymousinfo |o--o{ pms_adverseevent : "patient_id"
    pms_customercomplaint ||--o| pms_riskassessment : "complaint_id"
    auth_user ||--o{ pms_riskassessment : "assessed_by_id"
    auth_user |o--o{ pms_riskassessmenthistory : "actor_id"
    pms_riskassessment ||--o{ pms_riskassessmenthistory : "parent_id"
```

## CAPA·효과성 평가·후속 조치

```mermaid
erDiagram
    pms_capa {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey complaint_id FK
        CharField title
        TextField root_cause
        TextField corrective_action
        TextField preventive_action
        ForeignKey owner_id FK
        DateField due_date
        CharField status
        TextField action_result
        TextField evaluation_criteria
        DateField evaluation_due
    }
    pms_capaevaluation {
        BigAutoField id PK
        ForeignKey capa_id FK
        TextField action_result
        TextField criteria
        DateField scheduled_on
        ForeignKey evaluator_id FK
        DateField evaluated_on
        CharField verdict
        TextField rationale
        OneToOneField followup_id FK,UK
        DateTimeField created_at
    }
    pms_worktask {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey ra_profile_id FK
        ForeignKey complaint_id FK
        ForeignKey capa_id FK
        ForeignKey recall_id FK
        ForeignKey assignee_id FK
        CharField title
        TextField description
        CharField priority
        DateTimeField due_at
        CharField status
    }
    pms_taskhistory {
        BigAutoField id PK
        ForeignKey task_id FK
        ForeignKey actor_id FK
        DateTimeField created_at
        JSONField before
        JSONField after
    }
    pms_attachment {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey ra_profile_id FK
        ForeignKey complaint_id FK
        FileField file
        CharField original_name
        ForeignKey uploaded_by_id FK
        CharField scan_status
        CharField sha256
        CharField detected_type
        DateTimeField scanned_at
    }
    pms_capaevaluation_evidence {
        BigAutoField id PK
        ForeignKey capaevaluation_id FK
        ForeignKey attachment_id FK
    }
    pms_customercomplaint {
        BigAutoField id PK
    }
    auth_user {
        AutoField id PK
    }
    pms_regulatoryprofile {
        BigAutoField id PK
    }
    pms_recall {
        BigAutoField id PK
    }
    pms_customercomplaint ||--o{ pms_capa : "complaint_id"
    auth_user ||--o{ pms_capa : "owner_id"
    pms_capa ||--o{ pms_capaevaluation : "capa_id"
    auth_user ||--o{ pms_capaevaluation : "evaluator_id"
    pms_worktask |o--o| pms_capaevaluation : "followup_id"
    pms_regulatoryprofile |o--o{ pms_worktask : "ra_profile_id"
    pms_customercomplaint |o--o{ pms_worktask : "complaint_id"
    pms_capa |o--o{ pms_worktask : "capa_id"
    pms_recall |o--o{ pms_worktask : "recall_id"
    auth_user ||--o{ pms_worktask : "assignee_id"
    pms_worktask ||--o{ pms_taskhistory : "task_id"
    auth_user ||--o{ pms_taskhistory : "actor_id"
    pms_regulatoryprofile |o--o{ pms_attachment : "ra_profile_id"
    pms_customercomplaint |o--o{ pms_attachment : "complaint_id"
    auth_user ||--o{ pms_attachment : "uploaded_by_id"
    pms_capaevaluation ||--o{ pms_capaevaluation_evidence : "capaevaluation_id"
    pms_attachment ||--o{ pms_capaevaluation_evidence : "attachment_id"
```

## 리콜·대상·거래처·회수 원장

```mermaid
erDiagram
    pms_recall {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey complaint_id FK
        CharField title
        TextField reason
        CharField risk_level
        ForeignKey device_id FK
        PositiveIntegerField distributed_quantity
        PositiveIntegerField target_quantity
        PositiveIntegerField recovered_quantity
        DateField start_date
        DateField expected_end_date
        ForeignKey owner_id FK
        CharField approval_status
        TextField decision_reason
        CharField progress_status
        TextField closure_report
    }
    pms_recalltarget {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey recall_id FK
        ForeignKey lot_id FK
        CharField serial_number
        PositiveIntegerField target_quantity
    }
    pms_businesspartner {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        CharField name UK
    }
    pms_recallrecipient {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey recall_id FK
        ForeignKey lot_id FK
        ForeignKey partner_id FK
        CharField unit
        PositiveIntegerField target_quantity
        PositiveIntegerField recovered_total
        DateField notified_on
        CharField notification_method
        DateField replied_on
        CharField reply_status
        TextField unrecovered_reason
    }
    pms_recoveryentry {
        BigAutoField id PK
        CharField request_key
        ForeignKey recipient_id FK
        DateField recovered_on
        PositiveIntegerField quantity
        ForeignKey actor_id FK
        DateTimeField created_at
    }
    pms_recallcontact {
        BigAutoField id PK
        ForeignKey recipient_id FK
        DateTimeField contacted_at
        CharField method
        TextField note
        ForeignKey actor_id FK
        DateTimeField created_at
    }
    pms_customercomplaint {
        BigAutoField id PK
    }
    pms_medicaldevice {
        BigAutoField id PK
    }
    auth_user {
        AutoField id PK
    }
    pms_productlot {
        BigAutoField id PK
    }
    pms_customercomplaint |o--o{ pms_recall : "complaint_id"
    pms_medicaldevice ||--o{ pms_recall : "device_id"
    auth_user ||--o{ pms_recall : "owner_id"
    pms_recall ||--o{ pms_recalltarget : "recall_id"
    pms_productlot ||--o{ pms_recalltarget : "lot_id"
    pms_recall ||--o{ pms_recallrecipient : "recall_id"
    pms_productlot ||--o{ pms_recallrecipient : "lot_id"
    pms_businesspartner ||--o{ pms_recallrecipient : "partner_id"
    pms_recallrecipient ||--o{ pms_recoveryentry : "recipient_id"
    auth_user ||--o{ pms_recoveryentry : "actor_id"
    pms_recallrecipient ||--o{ pms_recallcontact : "recipient_id"
    auth_user ||--o{ pms_recallcontact : "actor_id"
```

## 규정·청크·규칙 버전·적용·개정 영향

```mermaid
erDiagram
    pms_regulationdocument {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        CharField title
        CharField issuer
        CharField jurisdiction
        ForeignKey device_id FK
        TextField scope_description
        CharField document_number
        CharField edition
        DateField published_on
        DateField effective_on
        CharField official_url
        FileField file
        CharField original_name
        ForeignKey uploaded_by_id FK
        CharField visibility
        BooleanField is_example
        CharField scan_status
        CharField sha256
        CharField detected_type
        DateTimeField scanned_at
        CharField extraction_status
        CharField extraction_note
        CharField review_status
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        TextField review_reason
    }
    pms_regulationchunk {
        BigAutoField id PK
        ForeignKey document_id FK
        PositiveIntegerField sequence
        PositiveIntegerField page
        CharField section
        PositiveIntegerField paragraph
        TextField text
        CharField content_hash
        JSONField search_tokens
    }
    pms_reportingrule {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        CharField name
        PositiveIntegerField version
        JSONField conditions
        CharField basis
        PositiveIntegerField days
        CharField day_type
        JSONField holidays
        DateField effective_on
        TextField change_reason
        BooleanField is_example
        UUIDField family_key
        ForeignKey supersedes_id FK
        CharField state
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        DateTimeField activated_at
        PositiveIntegerField revision
        CharField jurisdiction
        ForeignKey device_id FK
        TextField scope_description
        CharField reporting_authority
        TextField obligation_trigger
        TextField deadline_expression
        CharField deadline_unit
        BooleanField include_start
        TimeField deadline_time
        CharField timezone_name
        TextField exceptions
        DateField effective_until
        DateField holiday_verified_from
        DateField holiday_verified_until
        DateField holiday_checked_on
        JSONField unresolved_items
        JSONField source_expressions
        CharField origin
    }
    pms_rulecitation {
        BigAutoField id PK
        ForeignKey rule_id FK
        CharField field_name
        ForeignKey chunk_id FK
        TextField quote
        TextField interpretation
        ForeignKey created_by_id FK
        DateTimeField created_at
    }
    pms_rulepreview {
        BigAutoField id PK
        ForeignKey rule_id FK
        CharField fingerprint
        JSONField inputs
        JSONField result
        ForeignKey created_by_id FK
        DateTimeField created_at
    }
    pms_rulechange {
        BigAutoField id PK
        ForeignKey rule_id FK
        ForeignKey actor_id FK
        CharField action
        TextField reason
        JSONField before
        JSONField after
        DateTimeField created_at
    }
    pms_rulefamilylock {
        UUIDField key PK
    }
    pms_ruleapplication {
        BigAutoField id PK
        JSONField previous_snapshot
        ForeignKey complaint_id FK
        ForeignKey rule_id FK
        JSONField snapshot
        DateTimeField due_at
        ForeignKey actor_id FK
        TextField reason
        DateTimeField created_at
    }
    pms_regulatoryimpact {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey old_rule_id FK
        ForeignKey new_rule_id FK
        ForeignKey created_by_id FK
        JSONField snapshot
        BooleanField include_closed
    }
    pms_impactreview {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey analysis_id FK
        ForeignKey complaint_id FK
        OneToOneField task_id FK,UK
        CharField status
        JSONField snapshot
        BooleanField shortened
        TextField reason
        ForeignKey processed_by_id FK
        DateTimeField processed_at
        OneToOneField application_id FK,UK
    }
    pms_medicaldevice {
        BigAutoField id PK
    }
    auth_user {
        AutoField id PK
    }
    pms_customercomplaint {
        BigAutoField id PK
    }
    pms_worktask {
        BigAutoField id PK
    }
    pms_medicaldevice |o--o{ pms_regulationdocument : "device_id"
    auth_user ||--o{ pms_regulationdocument : "uploaded_by_id"
    auth_user |o--o{ pms_regulationdocument : "reviewed_by_id"
    pms_regulationdocument ||--o{ pms_regulationchunk : "document_id"
    pms_reportingrule |o--o{ pms_reportingrule : "supersedes_id"
    auth_user |o--o{ pms_reportingrule : "created_by_id"
    auth_user |o--o{ pms_reportingrule : "reviewed_by_id"
    auth_user |o--o{ pms_reportingrule : "approved_by_id"
    pms_medicaldevice |o--o{ pms_reportingrule : "device_id"
    pms_reportingrule ||--o{ pms_rulecitation : "rule_id"
    pms_regulationchunk ||--o{ pms_rulecitation : "chunk_id"
    auth_user ||--o{ pms_rulecitation : "created_by_id"
    pms_reportingrule ||--o{ pms_rulepreview : "rule_id"
    auth_user ||--o{ pms_rulepreview : "created_by_id"
    pms_reportingrule ||--o{ pms_rulechange : "rule_id"
    auth_user ||--o{ pms_rulechange : "actor_id"
    pms_customercomplaint ||--o{ pms_ruleapplication : "complaint_id"
    pms_reportingrule ||--o{ pms_ruleapplication : "rule_id"
    auth_user ||--o{ pms_ruleapplication : "actor_id"
    pms_reportingrule ||--o{ pms_regulatoryimpact : "old_rule_id"
    pms_reportingrule ||--o{ pms_regulatoryimpact : "new_rule_id"
    auth_user ||--o{ pms_regulatoryimpact : "created_by_id"
    pms_regulatoryimpact ||--o{ pms_impactreview : "analysis_id"
    pms_customercomplaint ||--o{ pms_impactreview : "complaint_id"
    pms_worktask ||--o| pms_impactreview : "task_id"
    auth_user |o--o{ pms_impactreview : "processed_by_id"
    pms_ruleapplication |o--o| pms_impactreview : "application_id"
```

## 승인·담당 업무·알림·감사

```mermaid
erDiagram
    pms_approval {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        BooleanField superseded
        CharField content_type
        PositiveIntegerField object_id
        ForeignKey requested_by_id FK
        ForeignKey decided_by_id FK
        CharField decision
        TextField reason
        JSONField snapshot
        DateTimeField decided_at
    }
    pms_worktask {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey ra_profile_id FK
        ForeignKey complaint_id FK
        ForeignKey capa_id FK
        ForeignKey recall_id FK
        ForeignKey assignee_id FK
        CharField title
        TextField description
        CharField priority
        DateTimeField due_at
        CharField status
    }
    pms_taskhistory {
        BigAutoField id PK
        ForeignKey task_id FK
        ForeignKey actor_id FK
        DateTimeField created_at
        JSONField before
        JSONField after
    }
    pms_notification {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey user_id FK
        CharField title
        TextField message
        CharField level
        DateTimeField due_at
        DateTimeField read_at
        CharField dedupe_key UK
    }
    pms_auditlog {
        BigAutoField id PK
        ForeignKey actor_id FK
        CharField action
        CharField object_type
        CharField object_id
        JSONField before
        JSONField after
        GenericIPAddressField ip_address
        DateTimeField created_at
    }
    pms_profile {
        BigAutoField id PK
        OneToOneField user_id FK,UK
        CharField role
        CharField timezone_name
    }
    pms_loginbucket {
        BigAutoField id PK
        CharField key UK
        PositiveIntegerField count
        DateTimeField expires_at
    }
    pms_assistantconversation {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey user_id FK
        CharField title
        BooleanField is_active
    }
    pms_assistantmessage {
        BigAutoField id PK
        ForeignKey conversation_id FK
        CharField role
        TextField content
        CharField intent
        DateTimeField created_at
    }
    auth_user {
        AutoField id PK
    }
    pms_regulatoryprofile {
        BigAutoField id PK
    }
    pms_customercomplaint {
        BigAutoField id PK
    }
    pms_capa {
        BigAutoField id PK
    }
    pms_recall {
        BigAutoField id PK
    }
    auth_user ||--o{ pms_approval : "requested_by_id"
    auth_user |o--o{ pms_approval : "decided_by_id"
    pms_regulatoryprofile |o--o{ pms_worktask : "ra_profile_id"
    pms_customercomplaint |o--o{ pms_worktask : "complaint_id"
    pms_capa |o--o{ pms_worktask : "capa_id"
    pms_recall |o--o{ pms_worktask : "recall_id"
    auth_user ||--o{ pms_worktask : "assignee_id"
    pms_worktask ||--o{ pms_taskhistory : "task_id"
    auth_user ||--o{ pms_taskhistory : "actor_id"
    auth_user ||--o{ pms_notification : "user_id"
    auth_user |o--o{ pms_auditlog : "actor_id"
    auth_user ||--o| pms_profile : "user_id"
    auth_user ||--o{ pms_assistantconversation : "user_id"
    pms_assistantconversation ||--o{ pms_assistantmessage : "conversation_id"
```

## 분석 수집·레코드·안전 신호·검토

```mermaid
erDiagram
    pms_analysisimport {
        BigAutoField id PK
        CharField filename
        BinaryField original
        CharField sha256
        ForeignKey actor_id FK
        BooleanField is_example
        JSONField errors
        PositiveIntegerField accepted
        DateTimeField created_at
    }
    pms_analysisrecord {
        BigAutoField id PK
        ForeignKey batch_id FK
        PositiveIntegerField row_number
        JSONField raw
        CharField source
        CharField record_id
        CharField identity UK
        CharField device
        CharField manufacturer
        CharField model
        DateField occurred_on
        DateField reported_on
        CharField event_type
        CharField seriousness
        TextField narrative
    }
    pms_analysisreview {
        BigAutoField id PK
        CharField key UK
        JSONField snapshot
        CharField status
        ForeignKey assignee_id FK
        DateTimeField updated_at
    }
    pms_analysisreviewhistory {
        BigAutoField id PK
        ForeignKey review_id FK
        ForeignKey actor_id FK
        ForeignKey assignee_id FK
        CharField before
        CharField after
        TextField note
        DateTimeField created_at
    }
    pms_safetysignal {
        BigAutoField id PK
        CharField key UK
        CharField scope
        JSONField snapshot
        CharField status
        ForeignKey assignee_id FK
        OneToOneField task_id FK,UK
        DateTimeField created_at
    }
    pms_safetyreview {
        BigAutoField id PK
        ForeignKey signal_id FK
        ForeignKey actor_id FK
        ForeignKey assignee_id FK
        CharField before
        CharField after
        TextField note
        JSONField links
        DateTimeField created_at
    }
    auth_user {
        AutoField id PK
    }
    pms_worktask {
        BigAutoField id PK
    }
    auth_user ||--o{ pms_analysisimport : "actor_id"
    pms_analysisimport ||--o{ pms_analysisrecord : "batch_id"
    auth_user ||--o{ pms_analysisreview : "assignee_id"
    pms_analysisreview ||--o{ pms_analysisreviewhistory : "review_id"
    auth_user ||--o{ pms_analysisreviewhistory : "actor_id"
    auth_user ||--o{ pms_analysisreviewhistory : "assignee_id"
    auth_user ||--o{ pms_safetysignal : "assignee_id"
    pms_worktask |o--o| pms_safetysignal : "task_id"
    pms_safetysignal ||--o{ pms_safetyreview : "signal_id"
    auth_user ||--o{ pms_safetyreview : "actor_id"
    auth_user ||--o{ pms_safetyreview : "assignee_id"
```

## 제출·보고서·증빙 (구현 모델만)

```mermaid
erDiagram
    pms_regulatoryreport {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey complaint_id FK
        CharField document_number UK
        BooleanField required
        JSONField checklist
        TextField investigation_result
        CharField status
        ForeignKey author_id FK
        ForeignKey reviewer_id FK
        ForeignKey approved_by_id FK
        DateTimeField approved_at
    }
    pms_regulatoryreporthistory {
        BigAutoField id PK
        ForeignKey actor_id FK
        DateTimeField created_at
        TextField reason
        CharField source
        JSONField before
        JSONField after
        ForeignKey parent_id FK
    }
    pms_reportartifact {
        BigAutoField id PK
        ForeignKey complaint_id FK
        CharField number
        PositiveIntegerField version
        JSONField snapshot
        FileField file
        FileField bundle
        CharField sha256
        CharField bundle_sha256
        ForeignKey generated_by_id FK
        DateTimeField generated_at
    }
    pms_attachment {
        BigAutoField id PK
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey ra_profile_id FK
        ForeignKey complaint_id FK
        FileField file
        CharField original_name
        ForeignKey uploaded_by_id FK
        CharField scan_status
        CharField sha256
        CharField detected_type
        DateTimeField scanned_at
    }
    pms_customercomplaint {
        BigAutoField id PK
    }
    auth_user {
        AutoField id PK
    }
    pms_regulatoryprofile {
        BigAutoField id PK
    }
    pms_customercomplaint ||--o{ pms_regulatoryreport : "complaint_id"
    auth_user ||--o{ pms_regulatoryreport : "author_id"
    auth_user |o--o{ pms_regulatoryreport : "reviewer_id"
    auth_user |o--o{ pms_regulatoryreport : "approved_by_id"
    auth_user |o--o{ pms_regulatoryreporthistory : "actor_id"
    pms_regulatoryreport ||--o{ pms_regulatoryreporthistory : "parent_id"
    pms_customercomplaint ||--o{ pms_reportartifact : "complaint_id"
    auth_user ||--o{ pms_reportartifact : "generated_by_id"
    pms_regulatoryprofile |o--o{ pms_attachment : "ra_profile_id"
    pms_customercomplaint |o--o{ pms_attachment : "complaint_id"
    auth_user ||--o{ pms_attachment : "uploaded_by_id"
```

## RA 1단계: 규제 프로필·요구사항·인허가·갱신·제출 패키지

```mermaid
erDiagram
    pms_regulatoryprofile {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey device_id FK
        CharField jurisdiction
        ForeignKey organization_id FK
        CharField organization_role
        CharField product_family
        CharField classification
        TextField classification_basis
        TextField intended_use
        TextField authorized_scope
        CharField applicability
        TextField rationale
        ForeignKey source_id FK
        CharField source_url
        DateField source_checked_on
        ForeignKey source_checked_by_id FK
        DateField effective_on
        DateField next_review_on
    }
    pms_rarequirement {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        CharField internal_id
        ForeignKey source_id FK
        ForeignKey clause_id FK
        CharField clause_reference
        CharField applicability
        TextField applicability_reason
        TextField activity
        TextField deliverable
        CharField fulfillment
        DateField due_on
        PositiveIntegerField review_interval_days
        DateField confirmed_on
        DateField next_review_on
        CharField source_url
        DateField source_checked_on
        ForeignKey source_checked_by_id FK
    }
    pms_marketingauthorization {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        CharField kind
        CharField number
        CharField authority
        DateField issued_on
        DateField expires_on
        TextField conditions
        CharField status
        DateField renewal_prepare_on
        TextField renewal_basis
        DateField verified_on
        CharField verification_source
    }
    pms_authorizationevent {
        BigAutoField id PK
        ForeignKey authorization_id FK
        CharField status
        TextField reason
        ForeignKey actor_id FK
        DateTimeField created_at
        JSONField snapshot
    }
    pms_submissionpackage {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey product_revision_id FK
        ForeignKey change_id FK
        ForeignKey authorization_id FK
        PositiveIntegerField version
        TextField content_description
        CharField receipt_reference
        ForeignKey receipt_id FK
        DateField recorded_submitted_on
        JSONField frozen_snapshot
    }
    pms_rarequirement_evidence {
        BigAutoField id PK
        ForeignKey rarequirement_id FK
        ForeignKey attachment_id FK
    }
    pms_rarequirement_tasks {
        BigAutoField id PK
        ForeignKey rarequirement_id FK
        ForeignKey worktask_id FK
    }
    pms_marketingauthorization_evidence {
        BigAutoField id PK
        ForeignKey marketingauthorization_id FK
        ForeignKey attachment_id FK
    }
    pms_marketingauthorization_tasks {
        BigAutoField id PK
        ForeignKey marketingauthorization_id FK
        ForeignKey worktask_id FK
    }
    pms_submissionpackage_evidence {
        BigAutoField id PK
        ForeignKey submissionpackage_id FK
        ForeignKey attachment_id FK
    }
    pms_submissionpackage_tasks {
        BigAutoField id PK
        ForeignKey submissionpackage_id FK
        ForeignKey worktask_id FK
    }
    auth_user {
        AutoField id PK
    }
    pms_medicaldevice {
        BigAutoField id PK
    }
    pms_businesspartner {
        BigAutoField id PK
    }
    pms_regulationdocument {
        BigAutoField id PK
    }
    pms_regulationchunk {
        BigAutoField id PK
    }
    pms_productrevision {
        BigAutoField id PK
    }
    pms_productchange {
        BigAutoField id PK
    }
    pms_attachment {
        BigAutoField id PK
    }
    pms_worktask {
        BigAutoField id PK
    }
    auth_user ||--o{ pms_regulatoryprofile : "owner_id"
    auth_user |o--o{ pms_regulatoryprofile : "reviewer_id"
    auth_user ||--o{ pms_regulatoryprofile : "created_by_id"
    auth_user |o--o{ pms_regulatoryprofile : "reviewed_by_id"
    auth_user |o--o{ pms_regulatoryprofile : "approved_by_id"
    pms_medicaldevice ||--o{ pms_regulatoryprofile : "device_id"
    pms_businesspartner ||--o{ pms_regulatoryprofile : "organization_id"
    pms_regulationdocument |o--o{ pms_regulatoryprofile : "source_id"
    auth_user |o--o{ pms_regulatoryprofile : "source_checked_by_id"
    auth_user ||--o{ pms_rarequirement : "owner_id"
    auth_user |o--o{ pms_rarequirement : "reviewer_id"
    auth_user ||--o{ pms_rarequirement : "created_by_id"
    auth_user |o--o{ pms_rarequirement : "reviewed_by_id"
    auth_user |o--o{ pms_rarequirement : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_rarequirement : "profile_id"
    pms_regulationdocument |o--o{ pms_rarequirement : "source_id"
    pms_regulationchunk |o--o{ pms_rarequirement : "clause_id"
    auth_user |o--o{ pms_rarequirement : "source_checked_by_id"
    auth_user ||--o{ pms_marketingauthorization : "owner_id"
    auth_user |o--o{ pms_marketingauthorization : "reviewer_id"
    auth_user ||--o{ pms_marketingauthorization : "created_by_id"
    auth_user |o--o{ pms_marketingauthorization : "reviewed_by_id"
    auth_user |o--o{ pms_marketingauthorization : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_marketingauthorization : "profile_id"
    pms_marketingauthorization ||--o{ pms_authorizationevent : "authorization_id"
    auth_user ||--o{ pms_authorizationevent : "actor_id"
    auth_user ||--o{ pms_submissionpackage : "owner_id"
    auth_user |o--o{ pms_submissionpackage : "reviewer_id"
    auth_user ||--o{ pms_submissionpackage : "created_by_id"
    auth_user |o--o{ pms_submissionpackage : "reviewed_by_id"
    auth_user |o--o{ pms_submissionpackage : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_submissionpackage : "profile_id"
    pms_productrevision |o--o{ pms_submissionpackage : "product_revision_id"
    pms_productchange |o--o{ pms_submissionpackage : "change_id"
    pms_marketingauthorization ||--o{ pms_submissionpackage : "authorization_id"
    pms_attachment |o--o{ pms_submissionpackage : "receipt_id"
    pms_rarequirement ||--o{ pms_rarequirement_evidence : "rarequirement_id"
    pms_attachment ||--o{ pms_rarequirement_evidence : "attachment_id"
    pms_rarequirement ||--o{ pms_rarequirement_tasks : "rarequirement_id"
    pms_worktask ||--o{ pms_rarequirement_tasks : "worktask_id"
    pms_marketingauthorization ||--o{ pms_marketingauthorization_evidence : "marketingauthorization_id"
    pms_attachment ||--o{ pms_marketingauthorization_evidence : "attachment_id"
    pms_marketingauthorization ||--o{ pms_marketingauthorization_tasks : "marketingauthorization_id"
    pms_worktask ||--o{ pms_marketingauthorization_tasks : "worktask_id"
    pms_submissionpackage ||--o{ pms_submissionpackage_evidence : "submissionpackage_id"
    pms_attachment ||--o{ pms_submissionpackage_evidence : "attachment_id"
    pms_submissionpackage ||--o{ pms_submissionpackage_tasks : "submissionpackage_id"
    pms_worktask ||--o{ pms_submissionpackage_tasks : "worktask_id"
```

## RA 2단계: 제품 변경·제품 버전·통제 문서·라벨

```mermaid
erDiagram
    pms_productrevision {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        CharField version
        TextField description
        ForeignKey previous_id FK
    }
    pms_productchange {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        CharField category
        ForeignKey from_revision_id FK
        ForeignKey to_revision_id FK
        TextField before_content
        TextField after_content
        TextField reason
        JSONField impact_checklist
        CharField submission_decision
        TextField decision_basis
        ForeignKey authorization_id FK
        DateField implemented_on
        TextField implementation_confirmation
    }
    pms_controlleddocument {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        CharField category
        CharField number
        PositiveIntegerField version
        TextField body
        ForeignKey primary_file_id FK
        DateField effective_on
        DateField next_review_on
        TextField change_reason
        ForeignKey supersedes_id FK
    }
    pms_labelversion {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        CharField artifact_type
        CharField language
        PositiveIntegerField version
        ForeignKey document_id FK
        ForeignKey product_revision_id FK
        ForeignKey authorization_id FK
        ForeignKey change_id FK
        ForeignKey udi_id FK
        JSONField review_checklist
        ForeignKey translation_reviewer_id FK
        DateField translation_reviewed_on
        TextField translation_notes
        DateField effective_on
        ForeignKey previous_id FK
        ForeignKey safety_action_id FK
        TextField safety_change_reason
    }
    pms_productrevision_evidence {
        BigAutoField id PK
        ForeignKey productrevision_id FK
        ForeignKey attachment_id FK
    }
    pms_productrevision_tasks {
        BigAutoField id PK
        ForeignKey productrevision_id FK
        ForeignKey worktask_id FK
    }
    pms_productchange_evidence {
        BigAutoField id PK
        ForeignKey productchange_id FK
        ForeignKey attachment_id FK
    }
    pms_productchange_tasks {
        BigAutoField id PK
        ForeignKey productchange_id FK
        ForeignKey worktask_id FK
    }
    pms_productchange_lots {
        BigAutoField id PK
        ForeignKey productchange_id FK
        ForeignKey productlot_id FK
    }
    pms_productchange_documents {
        BigAutoField id PK
        ForeignKey productchange_id FK
        ForeignKey controlleddocument_id FK
    }
    pms_controlleddocument_evidence {
        BigAutoField id PK
        ForeignKey controlleddocument_id FK
        ForeignKey attachment_id FK
    }
    pms_controlleddocument_tasks {
        BigAutoField id PK
        ForeignKey controlleddocument_id FK
        ForeignKey worktask_id FK
    }
    pms_labelversion_evidence {
        BigAutoField id PK
        ForeignKey labelversion_id FK
        ForeignKey attachment_id FK
    }
    pms_labelversion_tasks {
        BigAutoField id PK
        ForeignKey labelversion_id FK
        ForeignKey worktask_id FK
    }
    pms_labelversion_lots {
        BigAutoField id PK
        ForeignKey labelversion_id FK
        ForeignKey productlot_id FK
    }
    auth_user {
        AutoField id PK
    }
    pms_regulatoryprofile {
        BigAutoField id PK
    }
    pms_marketingauthorization {
        BigAutoField id PK
    }
    pms_attachment {
        BigAutoField id PK
    }
    pms_udi {
        BigAutoField id PK
    }
    pms_fieldsafetyaction {
        BigAutoField id PK
    }
    pms_worktask {
        BigAutoField id PK
    }
    pms_productlot {
        BigAutoField id PK
    }
    auth_user ||--o{ pms_productrevision : "owner_id"
    auth_user |o--o{ pms_productrevision : "reviewer_id"
    auth_user ||--o{ pms_productrevision : "created_by_id"
    auth_user |o--o{ pms_productrevision : "reviewed_by_id"
    auth_user |o--o{ pms_productrevision : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_productrevision : "profile_id"
    pms_productrevision |o--o{ pms_productrevision : "previous_id"
    auth_user ||--o{ pms_productchange : "owner_id"
    auth_user |o--o{ pms_productchange : "reviewer_id"
    auth_user ||--o{ pms_productchange : "created_by_id"
    auth_user |o--o{ pms_productchange : "reviewed_by_id"
    auth_user |o--o{ pms_productchange : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_productchange : "profile_id"
    pms_productrevision ||--o{ pms_productchange : "from_revision_id"
    pms_productrevision ||--o{ pms_productchange : "to_revision_id"
    pms_marketingauthorization |o--o{ pms_productchange : "authorization_id"
    auth_user ||--o{ pms_controlleddocument : "owner_id"
    auth_user |o--o{ pms_controlleddocument : "reviewer_id"
    auth_user ||--o{ pms_controlleddocument : "created_by_id"
    auth_user |o--o{ pms_controlleddocument : "reviewed_by_id"
    auth_user |o--o{ pms_controlleddocument : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_controlleddocument : "profile_id"
    pms_attachment |o--o{ pms_controlleddocument : "primary_file_id"
    pms_controlleddocument |o--o{ pms_controlleddocument : "supersedes_id"
    auth_user ||--o{ pms_labelversion : "owner_id"
    auth_user |o--o{ pms_labelversion : "reviewer_id"
    auth_user ||--o{ pms_labelversion : "created_by_id"
    auth_user |o--o{ pms_labelversion : "reviewed_by_id"
    auth_user |o--o{ pms_labelversion : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_labelversion : "profile_id"
    pms_controlleddocument ||--o{ pms_labelversion : "document_id"
    pms_productrevision ||--o{ pms_labelversion : "product_revision_id"
    pms_marketingauthorization |o--o{ pms_labelversion : "authorization_id"
    pms_productchange |o--o{ pms_labelversion : "change_id"
    pms_udi |o--o{ pms_labelversion : "udi_id"
    auth_user |o--o{ pms_labelversion : "translation_reviewer_id"
    pms_labelversion |o--o{ pms_labelversion : "previous_id"
    pms_fieldsafetyaction |o--o{ pms_labelversion : "safety_action_id"
    pms_productrevision ||--o{ pms_productrevision_evidence : "productrevision_id"
    pms_attachment ||--o{ pms_productrevision_evidence : "attachment_id"
    pms_productrevision ||--o{ pms_productrevision_tasks : "productrevision_id"
    pms_worktask ||--o{ pms_productrevision_tasks : "worktask_id"
    pms_productchange ||--o{ pms_productchange_evidence : "productchange_id"
    pms_attachment ||--o{ pms_productchange_evidence : "attachment_id"
    pms_productchange ||--o{ pms_productchange_tasks : "productchange_id"
    pms_worktask ||--o{ pms_productchange_tasks : "worktask_id"
    pms_productchange ||--o{ pms_productchange_lots : "productchange_id"
    pms_productlot ||--o{ pms_productchange_lots : "productlot_id"
    pms_productchange ||--o{ pms_productchange_documents : "productchange_id"
    pms_controlleddocument ||--o{ pms_productchange_documents : "controlleddocument_id"
    pms_controlleddocument ||--o{ pms_controlleddocument_evidence : "controlleddocument_id"
    pms_attachment ||--o{ pms_controlleddocument_evidence : "attachment_id"
    pms_controlleddocument ||--o{ pms_controlleddocument_tasks : "controlleddocument_id"
    pms_worktask ||--o{ pms_controlleddocument_tasks : "worktask_id"
    pms_labelversion ||--o{ pms_labelversion_evidence : "labelversion_id"
    pms_attachment ||--o{ pms_labelversion_evidence : "attachment_id"
    pms_labelversion ||--o{ pms_labelversion_tasks : "labelversion_id"
    pms_worktask ||--o{ pms_labelversion_tasks : "worktask_id"
    pms_labelversion ||--o{ pms_labelversion_lots : "labelversion_id"
    pms_productlot ||--o{ pms_labelversion_lots : "productlot_id"
```

## RA 3단계: 제품 위험관리·안전 정보·현장 조치·공급자

```mermaid
erDiagram
    pms_riskcriteria {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        PositiveIntegerField version
        TextField estimation_method
        TextField acceptance_criteria
        TextField basis
        ForeignKey document_id FK
    }
    pms_productrisk {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey criteria_id FK
        ForeignKey document_id FK
        TextField hazard
        TextField hazardous_situation
        TextField harm
        TextField estimate
        TextField controls
        TextField verification
        CharField residual_decision
        TextField residual_rationale
        TextField benefit_risk_rationale
        DateField next_review_on
    }
    pms_safetyinformation {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        CharField source_url
        CharField source_identifier
        DateField collected_on
        ForeignKey original_id FK
        CharField relevance
        TextField relevance_reason
        CharField reporting_decision
        TextField reporting_basis
        ForeignKey report_id FK
    }
    pms_fieldsafetyaction {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        CharField action_type
        ForeignKey information_id FK
        ForeignKey complaint_id FK
        ForeignKey signal_id FK
        ForeignKey capa_id FK
        OneToOneField recall_id FK,UK
        ForeignKey notice_document_id FK
        TextField rationale
        TextField effectiveness_criteria
        TextField closure_rationale
    }
    pms_fieldactionrecipient {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey action_id FK
        ForeignKey partner_id FK
        ForeignKey lot_id FK
        CharField unit
        PositiveIntegerField target_quantity
        PositiveIntegerField completed_quantity
        DateField notified_on
        DateField acknowledged_on
        DateField completed_on
        TextField outcome
    }
    pms_fieldactioncontact {
        BigAutoField id PK
        ForeignKey recipient_id FK
        ForeignKey actor_id FK
        DateTimeField contacted_at
        CharField method
        TextField note
        ForeignKey evidence_id FK
    }
    pms_fieldactionevaluation {
        BigAutoField id PK
        ForeignKey action_id FK
        ForeignKey actor_id FK
        DateTimeField evaluated_at
        CharField verdict
        TextField rationale
        ForeignKey evidence_id FK
        JSONField snapshot
    }
    pms_supplierrecord {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey partner_id FK
        CharField supplier_type
        CharField site_reference
        TextField process_service
        TextField evaluation_criteria
        ForeignKey criteria_document_id FK
        DateField next_review_on
        TextField nonconformity_reference
    }
    pms_suppliermaterial {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey supplier_id FK
        CharField category
        CharField version
        DateField issued_on
        DateField expires_on
        TextField deficiencies
        DateField next_review_on
        TextField change_notice
        TextField impact_review
    }
    pms_riskcriteria_evidence {
        BigAutoField id PK
        ForeignKey riskcriteria_id FK
        ForeignKey attachment_id FK
    }
    pms_riskcriteria_tasks {
        BigAutoField id PK
        ForeignKey riskcriteria_id FK
        ForeignKey worktask_id FK
    }
    pms_productrisk_evidence {
        BigAutoField id PK
        ForeignKey productrisk_id FK
        ForeignKey attachment_id FK
    }
    pms_productrisk_tasks {
        BigAutoField id PK
        ForeignKey productrisk_id FK
        ForeignKey worktask_id FK
    }
    pms_productrisk_complaints {
        BigAutoField id PK
        ForeignKey productrisk_id FK
        ForeignKey customercomplaint_id FK
    }
    pms_productrisk_adverse_events {
        BigAutoField id PK
        ForeignKey productrisk_id FK
        ForeignKey adverseevent_id FK
    }
    pms_productrisk_signals {
        BigAutoField id PK
        ForeignKey productrisk_id FK
        ForeignKey safetysignal_id FK
    }
    pms_productrisk_capas {
        BigAutoField id PK
        ForeignKey productrisk_id FK
        ForeignKey capa_id FK
    }
    pms_safetyinformation_evidence {
        BigAutoField id PK
        ForeignKey safetyinformation_id FK
        ForeignKey attachment_id FK
    }
    pms_safetyinformation_tasks {
        BigAutoField id PK
        ForeignKey safetyinformation_id FK
        ForeignKey worktask_id FK
    }
    pms_fieldsafetyaction_evidence {
        BigAutoField id PK
        ForeignKey fieldsafetyaction_id FK
        ForeignKey attachment_id FK
    }
    pms_fieldsafetyaction_tasks {
        BigAutoField id PK
        ForeignKey fieldsafetyaction_id FK
        ForeignKey worktask_id FK
    }
    pms_fieldactionrecipient_evidence {
        BigAutoField id PK
        ForeignKey fieldactionrecipient_id FK
        ForeignKey attachment_id FK
    }
    pms_fieldactionrecipient_tasks {
        BigAutoField id PK
        ForeignKey fieldactionrecipient_id FK
        ForeignKey worktask_id FK
    }
    pms_supplierrecord_evidence {
        BigAutoField id PK
        ForeignKey supplierrecord_id FK
        ForeignKey attachment_id FK
    }
    pms_supplierrecord_tasks {
        BigAutoField id PK
        ForeignKey supplierrecord_id FK
        ForeignKey worktask_id FK
    }
    pms_supplierrecord_capas {
        BigAutoField id PK
        ForeignKey supplierrecord_id FK
        ForeignKey capa_id FK
    }
    pms_suppliermaterial_evidence {
        BigAutoField id PK
        ForeignKey suppliermaterial_id FK
        ForeignKey attachment_id FK
    }
    pms_suppliermaterial_tasks {
        BigAutoField id PK
        ForeignKey suppliermaterial_id FK
        ForeignKey worktask_id FK
    }
    auth_user {
        AutoField id PK
    }
    pms_regulatoryprofile {
        BigAutoField id PK
    }
    pms_controlleddocument {
        BigAutoField id PK
    }
    pms_attachment {
        BigAutoField id PK
    }
    pms_regulatoryreport {
        BigAutoField id PK
    }
    pms_customercomplaint {
        BigAutoField id PK
    }
    pms_safetysignal {
        BigAutoField id PK
    }
    pms_capa {
        BigAutoField id PK
    }
    pms_recall {
        BigAutoField id PK
    }
    pms_businesspartner {
        BigAutoField id PK
    }
    pms_productlot {
        BigAutoField id PK
    }
    pms_worktask {
        BigAutoField id PK
    }
    pms_adverseevent {
        BigAutoField id PK
    }
    auth_user ||--o{ pms_riskcriteria : "owner_id"
    auth_user |o--o{ pms_riskcriteria : "reviewer_id"
    auth_user ||--o{ pms_riskcriteria : "created_by_id"
    auth_user |o--o{ pms_riskcriteria : "reviewed_by_id"
    auth_user |o--o{ pms_riskcriteria : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_riskcriteria : "profile_id"
    pms_controlleddocument |o--o{ pms_riskcriteria : "document_id"
    auth_user ||--o{ pms_productrisk : "owner_id"
    auth_user |o--o{ pms_productrisk : "reviewer_id"
    auth_user ||--o{ pms_productrisk : "created_by_id"
    auth_user |o--o{ pms_productrisk : "reviewed_by_id"
    auth_user |o--o{ pms_productrisk : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_productrisk : "profile_id"
    pms_riskcriteria ||--o{ pms_productrisk : "criteria_id"
    pms_controlleddocument |o--o{ pms_productrisk : "document_id"
    auth_user ||--o{ pms_safetyinformation : "owner_id"
    auth_user |o--o{ pms_safetyinformation : "reviewer_id"
    auth_user ||--o{ pms_safetyinformation : "created_by_id"
    auth_user |o--o{ pms_safetyinformation : "reviewed_by_id"
    auth_user |o--o{ pms_safetyinformation : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_safetyinformation : "profile_id"
    pms_attachment |o--o{ pms_safetyinformation : "original_id"
    pms_regulatoryreport |o--o{ pms_safetyinformation : "report_id"
    auth_user ||--o{ pms_fieldsafetyaction : "owner_id"
    auth_user |o--o{ pms_fieldsafetyaction : "reviewer_id"
    auth_user ||--o{ pms_fieldsafetyaction : "created_by_id"
    auth_user |o--o{ pms_fieldsafetyaction : "reviewed_by_id"
    auth_user |o--o{ pms_fieldsafetyaction : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_fieldsafetyaction : "profile_id"
    pms_safetyinformation |o--o{ pms_fieldsafetyaction : "information_id"
    pms_customercomplaint |o--o{ pms_fieldsafetyaction : "complaint_id"
    pms_safetysignal |o--o{ pms_fieldsafetyaction : "signal_id"
    pms_capa |o--o{ pms_fieldsafetyaction : "capa_id"
    pms_recall |o--o| pms_fieldsafetyaction : "recall_id"
    pms_controlleddocument ||--o{ pms_fieldsafetyaction : "notice_document_id"
    auth_user ||--o{ pms_fieldactionrecipient : "owner_id"
    auth_user |o--o{ pms_fieldactionrecipient : "reviewer_id"
    auth_user ||--o{ pms_fieldactionrecipient : "created_by_id"
    auth_user |o--o{ pms_fieldactionrecipient : "reviewed_by_id"
    auth_user |o--o{ pms_fieldactionrecipient : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_fieldactionrecipient : "profile_id"
    pms_fieldsafetyaction ||--o{ pms_fieldactionrecipient : "action_id"
    pms_businesspartner ||--o{ pms_fieldactionrecipient : "partner_id"
    pms_productlot ||--o{ pms_fieldactionrecipient : "lot_id"
    pms_fieldactionrecipient ||--o{ pms_fieldactioncontact : "recipient_id"
    auth_user ||--o{ pms_fieldactioncontact : "actor_id"
    pms_attachment |o--o{ pms_fieldactioncontact : "evidence_id"
    pms_fieldsafetyaction ||--o{ pms_fieldactionevaluation : "action_id"
    auth_user ||--o{ pms_fieldactionevaluation : "actor_id"
    pms_attachment ||--o{ pms_fieldactionevaluation : "evidence_id"
    auth_user ||--o{ pms_supplierrecord : "owner_id"
    auth_user |o--o{ pms_supplierrecord : "reviewer_id"
    auth_user ||--o{ pms_supplierrecord : "created_by_id"
    auth_user |o--o{ pms_supplierrecord : "reviewed_by_id"
    auth_user |o--o{ pms_supplierrecord : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_supplierrecord : "profile_id"
    pms_businesspartner ||--o{ pms_supplierrecord : "partner_id"
    pms_controlleddocument |o--o{ pms_supplierrecord : "criteria_document_id"
    auth_user ||--o{ pms_suppliermaterial : "owner_id"
    auth_user |o--o{ pms_suppliermaterial : "reviewer_id"
    auth_user ||--o{ pms_suppliermaterial : "created_by_id"
    auth_user |o--o{ pms_suppliermaterial : "reviewed_by_id"
    auth_user |o--o{ pms_suppliermaterial : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_suppliermaterial : "profile_id"
    pms_supplierrecord ||--o{ pms_suppliermaterial : "supplier_id"
    pms_riskcriteria ||--o{ pms_riskcriteria_evidence : "riskcriteria_id"
    pms_attachment ||--o{ pms_riskcriteria_evidence : "attachment_id"
    pms_riskcriteria ||--o{ pms_riskcriteria_tasks : "riskcriteria_id"
    pms_worktask ||--o{ pms_riskcriteria_tasks : "worktask_id"
    pms_productrisk ||--o{ pms_productrisk_evidence : "productrisk_id"
    pms_attachment ||--o{ pms_productrisk_evidence : "attachment_id"
    pms_productrisk ||--o{ pms_productrisk_tasks : "productrisk_id"
    pms_worktask ||--o{ pms_productrisk_tasks : "worktask_id"
    pms_productrisk ||--o{ pms_productrisk_complaints : "productrisk_id"
    pms_customercomplaint ||--o{ pms_productrisk_complaints : "customercomplaint_id"
    pms_productrisk ||--o{ pms_productrisk_adverse_events : "productrisk_id"
    pms_adverseevent ||--o{ pms_productrisk_adverse_events : "adverseevent_id"
    pms_productrisk ||--o{ pms_productrisk_signals : "productrisk_id"
    pms_safetysignal ||--o{ pms_productrisk_signals : "safetysignal_id"
    pms_productrisk ||--o{ pms_productrisk_capas : "productrisk_id"
    pms_capa ||--o{ pms_productrisk_capas : "capa_id"
    pms_safetyinformation ||--o{ pms_safetyinformation_evidence : "safetyinformation_id"
    pms_attachment ||--o{ pms_safetyinformation_evidence : "attachment_id"
    pms_safetyinformation ||--o{ pms_safetyinformation_tasks : "safetyinformation_id"
    pms_worktask ||--o{ pms_safetyinformation_tasks : "worktask_id"
    pms_fieldsafetyaction ||--o{ pms_fieldsafetyaction_evidence : "fieldsafetyaction_id"
    pms_attachment ||--o{ pms_fieldsafetyaction_evidence : "attachment_id"
    pms_fieldsafetyaction ||--o{ pms_fieldsafetyaction_tasks : "fieldsafetyaction_id"
    pms_worktask ||--o{ pms_fieldsafetyaction_tasks : "worktask_id"
    pms_fieldactionrecipient ||--o{ pms_fieldactionrecipient_evidence : "fieldactionrecipient_id"
    pms_attachment ||--o{ pms_fieldactionrecipient_evidence : "attachment_id"
    pms_fieldactionrecipient ||--o{ pms_fieldactionrecipient_tasks : "fieldactionrecipient_id"
    pms_worktask ||--o{ pms_fieldactionrecipient_tasks : "worktask_id"
    pms_supplierrecord ||--o{ pms_supplierrecord_evidence : "supplierrecord_id"
    pms_attachment ||--o{ pms_supplierrecord_evidence : "attachment_id"
    pms_supplierrecord ||--o{ pms_supplierrecord_tasks : "supplierrecord_id"
    pms_worktask ||--o{ pms_supplierrecord_tasks : "worktask_id"
    pms_supplierrecord ||--o{ pms_supplierrecord_capas : "supplierrecord_id"
    pms_capa ||--o{ pms_supplierrecord_capas : "capa_id"
    pms_suppliermaterial ||--o{ pms_suppliermaterial_evidence : "suppliermaterial_id"
    pms_attachment ||--o{ pms_suppliermaterial_evidence : "attachment_id"
    pms_suppliermaterial ||--o{ pms_suppliermaterial_tasks : "suppliermaterial_id"
    pms_worktask ||--o{ pms_suppliermaterial_tasks : "worktask_id"
```

## RA 4단계: 교육·감사·정기 검토·보존 정책

```mermaid
erDiagram
    pms_trainingrequirement {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey document_id FK
        CharField required_role
        DateField due_on
        TextField effectiveness_method
        BooleanField enforce_ra_approval
    }
    pms_trainingassignment {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        PositiveIntegerField attempt
        ForeignKey requirement_id FK
        ForeignKey trainee_id FK
        DateField due_on
        DateField completed_on
        ForeignKey completion_evidence_id FK
        CharField training_status
        CharField effectiveness
        TextField effectiveness_rationale
        ForeignKey retraining_of_id FK
    }
    pms_auditplan {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        CharField audit_type
        DateField scheduled_on
        TextField scope
        TextField criteria
        JSONField checklist
        TextField closure_rationale
    }
    pms_auditfinding {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey audit_id FK
        TextField observation
        CharField classification
        TextField classification_basis
        DateField due_on
        TextField response
        ForeignKey capa_id FK
        CharField effectiveness
        TextField effectiveness_rationale
    }
    pms_auditpackage {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey audit_id FK
        PositiveIntegerField version
        TextField description
        CharField receipt_reference
        JSONField frozen_snapshot
    }
    pms_managementreview {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        DateField period_start
        DateField period_end
        DateField meeting_on
        TextField unresolved_risks
        TextField meeting_notes
        JSONField management_snapshot
        DateTimeField captured_at
        ForeignKey pms_report_id FK
    }
    pms_managementdecision {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey review_id FK
        TextField decision
        TextField rationale
        DateField due_on
        DateField completed_on
        TextField outcome
    }
    pms_retentionpolicy {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey organization_id FK
        CharField record_category
        ForeignKey legal_source_id FK
        CharField source_url
        DateField checked_on
        TextField retention_basis
        PositiveIntegerField duration_days
        TextField disposal_procedure
        BooleanField automatic_deletion
    }
    pms_trainingrequirement_evidence {
        BigAutoField id PK
        ForeignKey trainingrequirement_id FK
        ForeignKey attachment_id FK
    }
    pms_trainingrequirement_tasks {
        BigAutoField id PK
        ForeignKey trainingrequirement_id FK
        ForeignKey worktask_id FK
    }
    pms_trainingassignment_evidence {
        BigAutoField id PK
        ForeignKey trainingassignment_id FK
        ForeignKey attachment_id FK
    }
    pms_trainingassignment_tasks {
        BigAutoField id PK
        ForeignKey trainingassignment_id FK
        ForeignKey worktask_id FK
    }
    pms_auditplan_evidence {
        BigAutoField id PK
        ForeignKey auditplan_id FK
        ForeignKey attachment_id FK
    }
    pms_auditplan_tasks {
        BigAutoField id PK
        ForeignKey auditplan_id FK
        ForeignKey worktask_id FK
    }
    pms_auditfinding_evidence {
        BigAutoField id PK
        ForeignKey auditfinding_id FK
        ForeignKey attachment_id FK
    }
    pms_auditfinding_tasks {
        BigAutoField id PK
        ForeignKey auditfinding_id FK
        ForeignKey worktask_id FK
    }
    pms_auditpackage_evidence {
        BigAutoField id PK
        ForeignKey auditpackage_id FK
        ForeignKey attachment_id FK
    }
    pms_auditpackage_tasks {
        BigAutoField id PK
        ForeignKey auditpackage_id FK
        ForeignKey worktask_id FK
    }
    pms_managementreview_evidence {
        BigAutoField id PK
        ForeignKey managementreview_id FK
        ForeignKey attachment_id FK
    }
    pms_managementreview_tasks {
        BigAutoField id PK
        ForeignKey managementreview_id FK
        ForeignKey worktask_id FK
    }
    pms_managementdecision_evidence {
        BigAutoField id PK
        ForeignKey managementdecision_id FK
        ForeignKey attachment_id FK
    }
    pms_managementdecision_tasks {
        BigAutoField id PK
        ForeignKey managementdecision_id FK
        ForeignKey worktask_id FK
    }
    auth_user {
        AutoField id PK
    }
    pms_regulatoryprofile {
        BigAutoField id PK
    }
    pms_controlleddocument {
        BigAutoField id PK
    }
    pms_attachment {
        BigAutoField id PK
    }
    pms_capa {
        BigAutoField id PK
    }
    pms_reportartifact {
        BigAutoField id PK
    }
    pms_businesspartner {
        BigAutoField id PK
    }
    pms_regulationdocument {
        BigAutoField id PK
    }
    pms_worktask {
        BigAutoField id PK
    }
    auth_user ||--o{ pms_trainingrequirement : "owner_id"
    auth_user |o--o{ pms_trainingrequirement : "reviewer_id"
    auth_user ||--o{ pms_trainingrequirement : "created_by_id"
    auth_user |o--o{ pms_trainingrequirement : "reviewed_by_id"
    auth_user |o--o{ pms_trainingrequirement : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_trainingrequirement : "profile_id"
    pms_controlleddocument ||--o{ pms_trainingrequirement : "document_id"
    auth_user ||--o{ pms_trainingassignment : "owner_id"
    auth_user |o--o{ pms_trainingassignment : "reviewer_id"
    auth_user ||--o{ pms_trainingassignment : "created_by_id"
    auth_user |o--o{ pms_trainingassignment : "reviewed_by_id"
    auth_user |o--o{ pms_trainingassignment : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_trainingassignment : "profile_id"
    pms_trainingrequirement ||--o{ pms_trainingassignment : "requirement_id"
    auth_user ||--o{ pms_trainingassignment : "trainee_id"
    pms_attachment |o--o{ pms_trainingassignment : "completion_evidence_id"
    pms_trainingassignment |o--o{ pms_trainingassignment : "retraining_of_id"
    auth_user ||--o{ pms_auditplan : "owner_id"
    auth_user |o--o{ pms_auditplan : "reviewer_id"
    auth_user ||--o{ pms_auditplan : "created_by_id"
    auth_user |o--o{ pms_auditplan : "reviewed_by_id"
    auth_user |o--o{ pms_auditplan : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_auditplan : "profile_id"
    auth_user ||--o{ pms_auditfinding : "owner_id"
    auth_user |o--o{ pms_auditfinding : "reviewer_id"
    auth_user ||--o{ pms_auditfinding : "created_by_id"
    auth_user |o--o{ pms_auditfinding : "reviewed_by_id"
    auth_user |o--o{ pms_auditfinding : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_auditfinding : "profile_id"
    pms_auditplan ||--o{ pms_auditfinding : "audit_id"
    pms_capa |o--o{ pms_auditfinding : "capa_id"
    auth_user ||--o{ pms_auditpackage : "owner_id"
    auth_user |o--o{ pms_auditpackage : "reviewer_id"
    auth_user ||--o{ pms_auditpackage : "created_by_id"
    auth_user |o--o{ pms_auditpackage : "reviewed_by_id"
    auth_user |o--o{ pms_auditpackage : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_auditpackage : "profile_id"
    pms_auditplan ||--o{ pms_auditpackage : "audit_id"
    auth_user ||--o{ pms_managementreview : "owner_id"
    auth_user |o--o{ pms_managementreview : "reviewer_id"
    auth_user ||--o{ pms_managementreview : "created_by_id"
    auth_user |o--o{ pms_managementreview : "reviewed_by_id"
    auth_user |o--o{ pms_managementreview : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_managementreview : "profile_id"
    pms_reportartifact |o--o{ pms_managementreview : "pms_report_id"
    auth_user ||--o{ pms_managementdecision : "owner_id"
    auth_user |o--o{ pms_managementdecision : "reviewer_id"
    auth_user ||--o{ pms_managementdecision : "created_by_id"
    auth_user |o--o{ pms_managementdecision : "reviewed_by_id"
    auth_user |o--o{ pms_managementdecision : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_managementdecision : "profile_id"
    pms_managementreview ||--o{ pms_managementdecision : "review_id"
    auth_user ||--o{ pms_retentionpolicy : "owner_id"
    auth_user |o--o{ pms_retentionpolicy : "reviewer_id"
    auth_user ||--o{ pms_retentionpolicy : "created_by_id"
    auth_user |o--o{ pms_retentionpolicy : "reviewed_by_id"
    auth_user |o--o{ pms_retentionpolicy : "approved_by_id"
    pms_businesspartner ||--o{ pms_retentionpolicy : "organization_id"
    pms_regulationdocument |o--o{ pms_retentionpolicy : "legal_source_id"
    pms_trainingrequirement ||--o{ pms_trainingrequirement_evidence : "trainingrequirement_id"
    pms_attachment ||--o{ pms_trainingrequirement_evidence : "attachment_id"
    pms_trainingrequirement ||--o{ pms_trainingrequirement_tasks : "trainingrequirement_id"
    pms_worktask ||--o{ pms_trainingrequirement_tasks : "worktask_id"
    pms_trainingassignment ||--o{ pms_trainingassignment_evidence : "trainingassignment_id"
    pms_attachment ||--o{ pms_trainingassignment_evidence : "attachment_id"
    pms_trainingassignment ||--o{ pms_trainingassignment_tasks : "trainingassignment_id"
    pms_worktask ||--o{ pms_trainingassignment_tasks : "worktask_id"
    pms_auditplan ||--o{ pms_auditplan_evidence : "auditplan_id"
    pms_attachment ||--o{ pms_auditplan_evidence : "attachment_id"
    pms_auditplan ||--o{ pms_auditplan_tasks : "auditplan_id"
    pms_worktask ||--o{ pms_auditplan_tasks : "worktask_id"
    pms_auditfinding ||--o{ pms_auditfinding_evidence : "auditfinding_id"
    pms_attachment ||--o{ pms_auditfinding_evidence : "attachment_id"
    pms_auditfinding ||--o{ pms_auditfinding_tasks : "auditfinding_id"
    pms_worktask ||--o{ pms_auditfinding_tasks : "worktask_id"
    pms_auditpackage ||--o{ pms_auditpackage_evidence : "auditpackage_id"
    pms_attachment ||--o{ pms_auditpackage_evidence : "attachment_id"
    pms_auditpackage ||--o{ pms_auditpackage_tasks : "auditpackage_id"
    pms_worktask ||--o{ pms_auditpackage_tasks : "worktask_id"
    pms_managementreview ||--o{ pms_managementreview_evidence : "managementreview_id"
    pms_attachment ||--o{ pms_managementreview_evidence : "attachment_id"
    pms_managementreview ||--o{ pms_managementreview_tasks : "managementreview_id"
    pms_worktask ||--o{ pms_managementreview_tasks : "worktask_id"
    pms_managementdecision ||--o{ pms_managementdecision_evidence : "managementdecision_id"
    pms_attachment ||--o{ pms_managementdecision_evidence : "attachment_id"
    pms_managementdecision ||--o{ pms_managementdecision_tasks : "managementdecision_id"
    pms_worktask ||--o{ pms_managementdecision_tasks : "worktask_id"
```

## RA 실무 1: GMP 문서 계층·양식·정정

```mermaid
erDiagram
    pms_qualitydocument {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey document_id FK
        ForeignKey parent_id FK
        CharField department
        CharField level
        ForeignKey training_id FK
        JSONField required_fields
        BooleanField template_approved
        ForeignKey template_source_id FK
    }
    pms_qualityrecord {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey form_version_id FK
        ForeignKey project_id FK
        ForeignKey lot_id FK
        ForeignKey change_id FK
        ForeignKey training_id FK
        ForeignKey capa_id FK
        DateField due_on
        CharField record_key
        JSONField values
        ForeignKey corrects_id FK
    }
    pms_qualitydocument_evidence {
        BigAutoField id PK
        ForeignKey qualitydocument_id FK
        ForeignKey attachment_id FK
    }
    pms_qualitydocument_tasks {
        BigAutoField id PK
        ForeignKey qualitydocument_id FK
        ForeignKey worktask_id FK
    }
    pms_qualitydocument_requirements {
        BigAutoField id PK
        ForeignKey qualitydocument_id FK
        ForeignKey rarequirement_id FK
    }
    pms_qualityrecord_evidence {
        BigAutoField id PK
        ForeignKey qualityrecord_id FK
        ForeignKey attachment_id FK
    }
    pms_qualityrecord_tasks {
        BigAutoField id PK
        ForeignKey qualityrecord_id FK
        ForeignKey worktask_id FK
    }
    auth_user {
        AutoField id PK
    }
    pms_regulatoryprofile {
        BigAutoField id PK
    }
    pms_controlleddocument {
        BigAutoField id PK
    }
    pms_trainingrequirement {
        BigAutoField id PK
    }
    pms_dhfproject {
        BigAutoField id PK
    }
    pms_productlot {
        BigAutoField id PK
    }
    pms_productchange {
        BigAutoField id PK
    }
    pms_trainingassignment {
        BigAutoField id PK
    }
    pms_capa {
        BigAutoField id PK
    }
    pms_attachment {
        BigAutoField id PK
    }
    pms_worktask {
        BigAutoField id PK
    }
    pms_rarequirement {
        BigAutoField id PK
    }
    auth_user ||--o{ pms_qualitydocument : "owner_id"
    auth_user |o--o{ pms_qualitydocument : "reviewer_id"
    auth_user ||--o{ pms_qualitydocument : "created_by_id"
    auth_user |o--o{ pms_qualitydocument : "reviewed_by_id"
    auth_user |o--o{ pms_qualitydocument : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_qualitydocument : "profile_id"
    pms_controlleddocument ||--o{ pms_qualitydocument : "document_id"
    pms_qualitydocument |o--o{ pms_qualitydocument : "parent_id"
    pms_trainingrequirement |o--o{ pms_qualitydocument : "training_id"
    pms_controlleddocument |o--o{ pms_qualitydocument : "template_source_id"
    auth_user ||--o{ pms_qualityrecord : "owner_id"
    auth_user |o--o{ pms_qualityrecord : "reviewer_id"
    auth_user ||--o{ pms_qualityrecord : "created_by_id"
    auth_user |o--o{ pms_qualityrecord : "reviewed_by_id"
    auth_user |o--o{ pms_qualityrecord : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_qualityrecord : "profile_id"
    pms_qualitydocument ||--o{ pms_qualityrecord : "form_version_id"
    pms_dhfproject |o--o{ pms_qualityrecord : "project_id"
    pms_productlot |o--o{ pms_qualityrecord : "lot_id"
    pms_productchange |o--o{ pms_qualityrecord : "change_id"
    pms_trainingassignment |o--o{ pms_qualityrecord : "training_id"
    pms_capa |o--o{ pms_qualityrecord : "capa_id"
    pms_qualityrecord |o--o{ pms_qualityrecord : "corrects_id"
    pms_qualitydocument ||--o{ pms_qualitydocument_evidence : "qualitydocument_id"
    pms_attachment ||--o{ pms_qualitydocument_evidence : "attachment_id"
    pms_qualitydocument ||--o{ pms_qualitydocument_tasks : "qualitydocument_id"
    pms_worktask ||--o{ pms_qualitydocument_tasks : "worktask_id"
    pms_qualitydocument ||--o{ pms_qualitydocument_requirements : "qualitydocument_id"
    pms_rarequirement ||--o{ pms_qualitydocument_requirements : "rarequirement_id"
    pms_qualityrecord ||--o{ pms_qualityrecord_evidence : "qualityrecord_id"
    pms_attachment ||--o{ pms_qualityrecord_evidence : "attachment_id"
    pms_qualityrecord ||--o{ pms_qualityrecord_tasks : "qualityrecord_id"
    pms_worktask ||--o{ pms_qualityrecord_tasks : "worktask_id"
```

## RA 실무 2: 품질시스템 밸리데이션

```mermaid
erDiagram
    pms_qualityvalidation {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        CharField system_version
        TextField intended_use
        TextField quality_impact
        TextField plan
        TextField acceptance
        TextField report
        ForeignKey supplier_material_id FK
        TextField internal_confirmation
        ForeignKey previous_id FK
        TextField revalidation_reason
    }
    pms_validationrequirement {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey validation_id FK
        TextField requirement
        TextField risk
        TextField control
    }
    pms_validationcase {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey requirement_id FK
        PositiveIntegerField version
        TextField procedure
        TextField expected
        ForeignKey previous_id FK
    }
    pms_validationrun {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey case_id FK
        CharField outcome
        TextField result
        TextField deviation
        ForeignKey retest_of_id FK
    }
    pms_qualityvalidation_evidence {
        BigAutoField id PK
        ForeignKey qualityvalidation_id FK
        ForeignKey attachment_id FK
    }
    pms_qualityvalidation_tasks {
        BigAutoField id PK
        ForeignKey qualityvalidation_id FK
        ForeignKey worktask_id FK
    }
    pms_validationrequirement_evidence {
        BigAutoField id PK
        ForeignKey validationrequirement_id FK
        ForeignKey attachment_id FK
    }
    pms_validationrequirement_tasks {
        BigAutoField id PK
        ForeignKey validationrequirement_id FK
        ForeignKey worktask_id FK
    }
    pms_validationcase_evidence {
        BigAutoField id PK
        ForeignKey validationcase_id FK
        ForeignKey attachment_id FK
    }
    pms_validationcase_tasks {
        BigAutoField id PK
        ForeignKey validationcase_id FK
        ForeignKey worktask_id FK
    }
    pms_validationrun_evidence {
        BigAutoField id PK
        ForeignKey validationrun_id FK
        ForeignKey attachment_id FK
    }
    pms_validationrun_tasks {
        BigAutoField id PK
        ForeignKey validationrun_id FK
        ForeignKey worktask_id FK
    }
    auth_user {
        AutoField id PK
    }
    pms_regulatoryprofile {
        BigAutoField id PK
    }
    pms_suppliermaterial {
        BigAutoField id PK
    }
    pms_attachment {
        BigAutoField id PK
    }
    pms_worktask {
        BigAutoField id PK
    }
    auth_user ||--o{ pms_qualityvalidation : "owner_id"
    auth_user |o--o{ pms_qualityvalidation : "reviewer_id"
    auth_user ||--o{ pms_qualityvalidation : "created_by_id"
    auth_user |o--o{ pms_qualityvalidation : "reviewed_by_id"
    auth_user |o--o{ pms_qualityvalidation : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_qualityvalidation : "profile_id"
    pms_suppliermaterial |o--o{ pms_qualityvalidation : "supplier_material_id"
    pms_qualityvalidation |o--o{ pms_qualityvalidation : "previous_id"
    auth_user ||--o{ pms_validationrequirement : "owner_id"
    auth_user |o--o{ pms_validationrequirement : "reviewer_id"
    auth_user ||--o{ pms_validationrequirement : "created_by_id"
    auth_user |o--o{ pms_validationrequirement : "reviewed_by_id"
    auth_user |o--o{ pms_validationrequirement : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_validationrequirement : "profile_id"
    pms_qualityvalidation ||--o{ pms_validationrequirement : "validation_id"
    auth_user ||--o{ pms_validationcase : "owner_id"
    auth_user |o--o{ pms_validationcase : "reviewer_id"
    auth_user ||--o{ pms_validationcase : "created_by_id"
    auth_user |o--o{ pms_validationcase : "reviewed_by_id"
    auth_user |o--o{ pms_validationcase : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_validationcase : "profile_id"
    pms_validationrequirement ||--o{ pms_validationcase : "requirement_id"
    pms_validationcase |o--o{ pms_validationcase : "previous_id"
    auth_user ||--o{ pms_validationrun : "owner_id"
    auth_user |o--o{ pms_validationrun : "reviewer_id"
    auth_user ||--o{ pms_validationrun : "created_by_id"
    auth_user |o--o{ pms_validationrun : "reviewed_by_id"
    auth_user |o--o{ pms_validationrun : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_validationrun : "profile_id"
    pms_validationcase ||--o{ pms_validationrun : "case_id"
    pms_validationrun |o--o{ pms_validationrun : "retest_of_id"
    pms_qualityvalidation ||--o{ pms_qualityvalidation_evidence : "qualityvalidation_id"
    pms_attachment ||--o{ pms_qualityvalidation_evidence : "attachment_id"
    pms_qualityvalidation ||--o{ pms_qualityvalidation_tasks : "qualityvalidation_id"
    pms_worktask ||--o{ pms_qualityvalidation_tasks : "worktask_id"
    pms_validationrequirement ||--o{ pms_validationrequirement_evidence : "validationrequirement_id"
    pms_attachment ||--o{ pms_validationrequirement_evidence : "attachment_id"
    pms_validationrequirement ||--o{ pms_validationrequirement_tasks : "validationrequirement_id"
    pms_worktask ||--o{ pms_validationrequirement_tasks : "worktask_id"
    pms_validationcase ||--o{ pms_validationcase_evidence : "validationcase_id"
    pms_attachment ||--o{ pms_validationcase_evidence : "attachment_id"
    pms_validationcase ||--o{ pms_validationcase_tasks : "validationcase_id"
    pms_worktask ||--o{ pms_validationcase_tasks : "worktask_id"
    pms_validationrun ||--o{ pms_validationrun_evidence : "validationrun_id"
    pms_attachment ||--o{ pms_validationrun_evidence : "attachment_id"
    pms_validationrun ||--o{ pms_validationrun_tasks : "validationrun_id"
    pms_worktask ||--o{ pms_validationrun_tasks : "worktask_id"
```

## RA 실무 3: 회의록 후보·DHF

```mermaid
erDiagram
    pms_dhfproject {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey release_id FK
        TextField purpose
    }
    pms_meetingsource {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey project_id FK
        ForeignKey minutes_id FK
        DateField meeting_on
    }
    pms_meetingcandidate {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey meeting_id FK
        PositiveIntegerField line_number
        TextField excerpt
        CharField category
        ForeignKey document_id FK
        ForeignKey mentioned_file_id FK
        CharField suggested_owner
        CharField suggested_due
        TextField uncertainty
        ForeignKey confirmed_trace_id FK
    }
    pms_designtrace {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey project_id FK
        ForeignKey requirement_id FK
        ForeignKey output_id FK
        ForeignKey risk_id FK
        ForeignKey verification_id FK
        ForeignKey change_id FK
        ForeignKey release_review_id FK
    }
    pms_dhfbaseline {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey project_id FK
        JSONField baseline
    }
    pms_dhfproject_evidence {
        BigAutoField id PK
        ForeignKey dhfproject_id FK
        ForeignKey attachment_id FK
    }
    pms_dhfproject_tasks {
        BigAutoField id PK
        ForeignKey dhfproject_id FK
        ForeignKey worktask_id FK
    }
    pms_meetingsource_evidence {
        BigAutoField id PK
        ForeignKey meetingsource_id FK
        ForeignKey attachment_id FK
    }
    pms_meetingsource_tasks {
        BigAutoField id PK
        ForeignKey meetingsource_id FK
        ForeignKey worktask_id FK
    }
    pms_meetingcandidate_evidence {
        BigAutoField id PK
        ForeignKey meetingcandidate_id FK
        ForeignKey attachment_id FK
    }
    pms_meetingcandidate_tasks {
        BigAutoField id PK
        ForeignKey meetingcandidate_id FK
        ForeignKey worktask_id FK
    }
    pms_designtrace_evidence {
        BigAutoField id PK
        ForeignKey designtrace_id FK
        ForeignKey attachment_id FK
    }
    pms_designtrace_tasks {
        BigAutoField id PK
        ForeignKey designtrace_id FK
        ForeignKey worktask_id FK
    }
    pms_dhfbaseline_evidence {
        BigAutoField id PK
        ForeignKey dhfbaseline_id FK
        ForeignKey attachment_id FK
    }
    pms_dhfbaseline_tasks {
        BigAutoField id PK
        ForeignKey dhfbaseline_id FK
        ForeignKey worktask_id FK
    }
    auth_user {
        AutoField id PK
    }
    pms_regulatoryprofile {
        BigAutoField id PK
    }
    pms_productrevision {
        BigAutoField id PK
    }
    pms_attachment {
        BigAutoField id PK
    }
    pms_controlleddocument {
        BigAutoField id PK
    }
    pms_rarequirement {
        BigAutoField id PK
    }
    pms_productrisk {
        BigAutoField id PK
    }
    pms_productchange {
        BigAutoField id PK
    }
    pms_worktask {
        BigAutoField id PK
    }
    auth_user ||--o{ pms_dhfproject : "owner_id"
    auth_user |o--o{ pms_dhfproject : "reviewer_id"
    auth_user ||--o{ pms_dhfproject : "created_by_id"
    auth_user |o--o{ pms_dhfproject : "reviewed_by_id"
    auth_user |o--o{ pms_dhfproject : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_dhfproject : "profile_id"
    pms_productrevision ||--o{ pms_dhfproject : "release_id"
    auth_user ||--o{ pms_meetingsource : "owner_id"
    auth_user |o--o{ pms_meetingsource : "reviewer_id"
    auth_user ||--o{ pms_meetingsource : "created_by_id"
    auth_user |o--o{ pms_meetingsource : "reviewed_by_id"
    auth_user |o--o{ pms_meetingsource : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_meetingsource : "profile_id"
    pms_dhfproject ||--o{ pms_meetingsource : "project_id"
    pms_attachment ||--o{ pms_meetingsource : "minutes_id"
    auth_user ||--o{ pms_meetingcandidate : "owner_id"
    auth_user |o--o{ pms_meetingcandidate : "reviewer_id"
    auth_user ||--o{ pms_meetingcandidate : "created_by_id"
    auth_user |o--o{ pms_meetingcandidate : "reviewed_by_id"
    auth_user |o--o{ pms_meetingcandidate : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_meetingcandidate : "profile_id"
    pms_meetingsource ||--o{ pms_meetingcandidate : "meeting_id"
    pms_controlleddocument |o--o{ pms_meetingcandidate : "document_id"
    pms_attachment |o--o{ pms_meetingcandidate : "mentioned_file_id"
    pms_designtrace |o--o{ pms_meetingcandidate : "confirmed_trace_id"
    auth_user ||--o{ pms_designtrace : "owner_id"
    auth_user |o--o{ pms_designtrace : "reviewer_id"
    auth_user ||--o{ pms_designtrace : "created_by_id"
    auth_user |o--o{ pms_designtrace : "reviewed_by_id"
    auth_user |o--o{ pms_designtrace : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_designtrace : "profile_id"
    pms_dhfproject ||--o{ pms_designtrace : "project_id"
    pms_rarequirement |o--o{ pms_designtrace : "requirement_id"
    pms_controlleddocument |o--o{ pms_designtrace : "output_id"
    pms_productrisk |o--o{ pms_designtrace : "risk_id"
    pms_controlleddocument |o--o{ pms_designtrace : "verification_id"
    pms_productchange |o--o{ pms_designtrace : "change_id"
    pms_productrevision |o--o{ pms_designtrace : "release_review_id"
    auth_user ||--o{ pms_dhfbaseline : "owner_id"
    auth_user |o--o{ pms_dhfbaseline : "reviewer_id"
    auth_user ||--o{ pms_dhfbaseline : "created_by_id"
    auth_user |o--o{ pms_dhfbaseline : "reviewed_by_id"
    auth_user |o--o{ pms_dhfbaseline : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_dhfbaseline : "profile_id"
    pms_dhfproject ||--o{ pms_dhfbaseline : "project_id"
    pms_dhfproject ||--o{ pms_dhfproject_evidence : "dhfproject_id"
    pms_attachment ||--o{ pms_dhfproject_evidence : "attachment_id"
    pms_dhfproject ||--o{ pms_dhfproject_tasks : "dhfproject_id"
    pms_worktask ||--o{ pms_dhfproject_tasks : "worktask_id"
    pms_meetingsource ||--o{ pms_meetingsource_evidence : "meetingsource_id"
    pms_attachment ||--o{ pms_meetingsource_evidence : "attachment_id"
    pms_meetingsource ||--o{ pms_meetingsource_tasks : "meetingsource_id"
    pms_worktask ||--o{ pms_meetingsource_tasks : "worktask_id"
    pms_meetingcandidate ||--o{ pms_meetingcandidate_evidence : "meetingcandidate_id"
    pms_attachment ||--o{ pms_meetingcandidate_evidence : "attachment_id"
    pms_meetingcandidate ||--o{ pms_meetingcandidate_tasks : "meetingcandidate_id"
    pms_worktask ||--o{ pms_meetingcandidate_tasks : "worktask_id"
    pms_designtrace ||--o{ pms_designtrace_evidence : "designtrace_id"
    pms_attachment ||--o{ pms_designtrace_evidence : "attachment_id"
    pms_designtrace ||--o{ pms_designtrace_tasks : "designtrace_id"
    pms_worktask ||--o{ pms_designtrace_tasks : "worktask_id"
    pms_dhfbaseline ||--o{ pms_dhfbaseline_evidence : "dhfbaseline_id"
    pms_attachment ||--o{ pms_dhfbaseline_evidence : "attachment_id"
    pms_dhfbaseline ||--o{ pms_dhfbaseline_tasks : "dhfbaseline_id"
    pms_worktask ||--o{ pms_dhfbaseline_tasks : "worktask_id"
```

## RA 실무 4: 소프트웨어 변경심사

```mermaid
erDiagram
    pms_softwarechangereview {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey change_id FK
        ForeignKey project_id FK
        CharField classification
        TextField classification_basis
        TextField function_comparison
        TextField algorithm_comparison
        TextField intended_use_comparison
        ForeignKey package_id FK
        JSONField submission_manifest
    }
    pms_technicalsection {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey review_id FK
        CharField section
        ForeignKey document_id FK
        CharField readiness
    }
    pms_reviewresponse {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey review_id FK
        TextField question
        TextField response
        ForeignKey package_id FK
        ForeignKey previous_id FK
    }
    pms_softwarechangereview_evidence {
        BigAutoField id PK
        ForeignKey softwarechangereview_id FK
        ForeignKey attachment_id FK
    }
    pms_softwarechangereview_tasks {
        BigAutoField id PK
        ForeignKey softwarechangereview_id FK
        ForeignKey worktask_id FK
    }
    pms_technicalsection_evidence {
        BigAutoField id PK
        ForeignKey technicalsection_id FK
        ForeignKey attachment_id FK
    }
    pms_technicalsection_tasks {
        BigAutoField id PK
        ForeignKey technicalsection_id FK
        ForeignKey worktask_id FK
    }
    pms_reviewresponse_evidence {
        BigAutoField id PK
        ForeignKey reviewresponse_id FK
        ForeignKey attachment_id FK
    }
    pms_reviewresponse_tasks {
        BigAutoField id PK
        ForeignKey reviewresponse_id FK
        ForeignKey worktask_id FK
    }
    auth_user {
        AutoField id PK
    }
    pms_regulatoryprofile {
        BigAutoField id PK
    }
    pms_productchange {
        BigAutoField id PK
    }
    pms_dhfproject {
        BigAutoField id PK
    }
    pms_submissionpackage {
        BigAutoField id PK
    }
    pms_controlleddocument {
        BigAutoField id PK
    }
    pms_attachment {
        BigAutoField id PK
    }
    pms_worktask {
        BigAutoField id PK
    }
    auth_user ||--o{ pms_softwarechangereview : "owner_id"
    auth_user |o--o{ pms_softwarechangereview : "reviewer_id"
    auth_user ||--o{ pms_softwarechangereview : "created_by_id"
    auth_user |o--o{ pms_softwarechangereview : "reviewed_by_id"
    auth_user |o--o{ pms_softwarechangereview : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_softwarechangereview : "profile_id"
    pms_productchange ||--o{ pms_softwarechangereview : "change_id"
    pms_dhfproject ||--o{ pms_softwarechangereview : "project_id"
    pms_submissionpackage |o--o{ pms_softwarechangereview : "package_id"
    auth_user ||--o{ pms_technicalsection : "owner_id"
    auth_user |o--o{ pms_technicalsection : "reviewer_id"
    auth_user ||--o{ pms_technicalsection : "created_by_id"
    auth_user |o--o{ pms_technicalsection : "reviewed_by_id"
    auth_user |o--o{ pms_technicalsection : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_technicalsection : "profile_id"
    pms_softwarechangereview ||--o{ pms_technicalsection : "review_id"
    pms_controlleddocument |o--o{ pms_technicalsection : "document_id"
    auth_user ||--o{ pms_reviewresponse : "owner_id"
    auth_user |o--o{ pms_reviewresponse : "reviewer_id"
    auth_user ||--o{ pms_reviewresponse : "created_by_id"
    auth_user |o--o{ pms_reviewresponse : "reviewed_by_id"
    auth_user |o--o{ pms_reviewresponse : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_reviewresponse : "profile_id"
    pms_softwarechangereview ||--o{ pms_reviewresponse : "review_id"
    pms_submissionpackage |o--o{ pms_reviewresponse : "package_id"
    pms_reviewresponse |o--o{ pms_reviewresponse : "previous_id"
    pms_softwarechangereview ||--o{ pms_softwarechangereview_evidence : "softwarechangereview_id"
    pms_attachment ||--o{ pms_softwarechangereview_evidence : "attachment_id"
    pms_softwarechangereview ||--o{ pms_softwarechangereview_tasks : "softwarechangereview_id"
    pms_worktask ||--o{ pms_softwarechangereview_tasks : "worktask_id"
    pms_technicalsection ||--o{ pms_technicalsection_evidence : "technicalsection_id"
    pms_attachment ||--o{ pms_technicalsection_evidence : "attachment_id"
    pms_technicalsection ||--o{ pms_technicalsection_tasks : "technicalsection_id"
    pms_worktask ||--o{ pms_technicalsection_tasks : "worktask_id"
    pms_reviewresponse ||--o{ pms_reviewresponse_evidence : "reviewresponse_id"
    pms_attachment ||--o{ pms_reviewresponse_evidence : "attachment_id"
    pms_reviewresponse ||--o{ pms_reviewresponse_tasks : "reviewresponse_id"
    pms_worktask ||--o{ pms_reviewresponse_tasks : "worktask_id"
```

## RA 실무 5: 사이버보안

```mermaid
erDiagram
    pms_securityinventory {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey release_id FK
        ForeignKey sbom_id FK
        TextField assets
        TextField interfaces
        JSONField components
    }
    pms_securityfinding {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey inventory_id FK
        CharField identifier
        CharField source
        DateField checked_on
        TextField threat
        TextField impact
        TextField assessment
        CharField score_source_version
        CharField score_as_reported
        DateField due_on
        TextField patch
        TextField residual
        ForeignKey risk_id FK
        ForeignKey change_id FK
        ForeignKey capa_id FK
        ForeignKey action_id FK
    }
    pms_securityreview {
        BigAutoField id PK
        CharField title
        ForeignKey owner_id FK
        ForeignKey reviewer_id FK
        ForeignKey created_by_id FK
        ForeignKey reviewed_by_id FK
        DateTimeField reviewed_at
        ForeignKey approved_by_id FK
        DateTimeField approved_at
        JSONField approval_snapshot
        CharField state
        PositiveIntegerField revision
        BooleanField is_example
        DateTimeField created_at
        DateTimeField updated_at
        ForeignKey profile_id FK
        ForeignKey inventory_id FK
        TextField test_plan
        TextField test_results
        TextField open_items
        TextField residual_decision
    }
    pms_securityinventory_evidence {
        BigAutoField id PK
        ForeignKey securityinventory_id FK
        ForeignKey attachment_id FK
    }
    pms_securityinventory_tasks {
        BigAutoField id PK
        ForeignKey securityinventory_id FK
        ForeignKey worktask_id FK
    }
    pms_securityfinding_evidence {
        BigAutoField id PK
        ForeignKey securityfinding_id FK
        ForeignKey attachment_id FK
    }
    pms_securityfinding_tasks {
        BigAutoField id PK
        ForeignKey securityfinding_id FK
        ForeignKey worktask_id FK
    }
    pms_securityreview_evidence {
        BigAutoField id PK
        ForeignKey securityreview_id FK
        ForeignKey attachment_id FK
    }
    pms_securityreview_tasks {
        BigAutoField id PK
        ForeignKey securityreview_id FK
        ForeignKey worktask_id FK
    }
    auth_user {
        AutoField id PK
    }
    pms_regulatoryprofile {
        BigAutoField id PK
    }
    pms_productrevision {
        BigAutoField id PK
    }
    pms_attachment {
        BigAutoField id PK
    }
    pms_productrisk {
        BigAutoField id PK
    }
    pms_productchange {
        BigAutoField id PK
    }
    pms_capa {
        BigAutoField id PK
    }
    pms_fieldsafetyaction {
        BigAutoField id PK
    }
    pms_worktask {
        BigAutoField id PK
    }
    auth_user ||--o{ pms_securityinventory : "owner_id"
    auth_user |o--o{ pms_securityinventory : "reviewer_id"
    auth_user ||--o{ pms_securityinventory : "created_by_id"
    auth_user |o--o{ pms_securityinventory : "reviewed_by_id"
    auth_user |o--o{ pms_securityinventory : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_securityinventory : "profile_id"
    pms_productrevision ||--o{ pms_securityinventory : "release_id"
    pms_attachment |o--o{ pms_securityinventory : "sbom_id"
    auth_user ||--o{ pms_securityfinding : "owner_id"
    auth_user |o--o{ pms_securityfinding : "reviewer_id"
    auth_user ||--o{ pms_securityfinding : "created_by_id"
    auth_user |o--o{ pms_securityfinding : "reviewed_by_id"
    auth_user |o--o{ pms_securityfinding : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_securityfinding : "profile_id"
    pms_securityinventory ||--o{ pms_securityfinding : "inventory_id"
    pms_productrisk |o--o{ pms_securityfinding : "risk_id"
    pms_productchange |o--o{ pms_securityfinding : "change_id"
    pms_capa |o--o{ pms_securityfinding : "capa_id"
    pms_fieldsafetyaction |o--o{ pms_securityfinding : "action_id"
    auth_user ||--o{ pms_securityreview : "owner_id"
    auth_user |o--o{ pms_securityreview : "reviewer_id"
    auth_user ||--o{ pms_securityreview : "created_by_id"
    auth_user |o--o{ pms_securityreview : "reviewed_by_id"
    auth_user |o--o{ pms_securityreview : "approved_by_id"
    pms_regulatoryprofile ||--o{ pms_securityreview : "profile_id"
    pms_securityinventory ||--o{ pms_securityreview : "inventory_id"
    pms_securityinventory ||--o{ pms_securityinventory_evidence : "securityinventory_id"
    pms_attachment ||--o{ pms_securityinventory_evidence : "attachment_id"
    pms_securityinventory ||--o{ pms_securityinventory_tasks : "securityinventory_id"
    pms_worktask ||--o{ pms_securityinventory_tasks : "worktask_id"
    pms_securityfinding ||--o{ pms_securityfinding_evidence : "securityfinding_id"
    pms_attachment ||--o{ pms_securityfinding_evidence : "attachment_id"
    pms_securityfinding ||--o{ pms_securityfinding_tasks : "securityfinding_id"
    pms_worktask ||--o{ pms_securityfinding_tasks : "worktask_id"
    pms_securityreview ||--o{ pms_securityreview_evidence : "securityreview_id"
    pms_attachment ||--o{ pms_securityreview_evidence : "attachment_id"
    pms_securityreview ||--o{ pms_securityreview_tasks : "securityreview_id"
    pms_worktask ||--o{ pms_securityreview_tasks : "worktask_id"
```
