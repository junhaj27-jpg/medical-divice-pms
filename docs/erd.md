# MedWatch PMS ERD

## 도메인 개요

사건은 제품·UDI·선택 LOT를 참조하며 위험평가, 이상사례, CAPA, 보고서, 리콜 및 업무를 모은다. 규칙은 원문 청크를 인용하는 버전으로 관리하고 사건 적용은 당시 스냅샷을 남긴다. 외부 CSV 분석 레코드는 제품 문자열을 사용하며 내부 제품 FK로 자동 연결하지 않는다.

기존 구현: 아래 물리 관계 중 두 History 테이블을 제외한 모델. 이번 추가: RiskAssessmentHistory·RegulatoryReportHistory, 삭제 보호, 제약과 조회 인덱스. 향후 제안: 제출 접수증 전용 엔터티, 안전 신호의 JSON 증거·조치 연결을 명시적 FK 연결 테이블로 전환, 범용 승인 대상의 명시 FK 전환. 제안은 아래 ERD에 구현처럼 표시하지 않았다.

## 물리 ERD 표기

`||` 필수 1, `o|` 선택 0..1, `o{` 선택 0..N. 자식의 FK null 여부가 부모 쪽 선택성을 결정한다. OneToOne은 자식 쪽 0..1이다. 모든 자식 FK 관계의 부모는 자식을 갖지 않을 수 있다. N:M은 실제 중간 테이블의 두 1:N 관계로 표시한다. 필드는 실제 DB column이며 PK/FK/UK를 표시한다. 타입은 Django 물리 필드 타입이며 DB별 SQL 매핑은 데이터 사전에 적었다. 반복 엔터티는 같은 테이블이다.

Approval.content_type/object_id, AuditLog.object_type/object_id, SafetyReview.links, 신호 snapshot의 evidence IDs는 논리 참조이며 FK 선을 그리지 않았다. family_key도 RuleFamilyLock.key에 대한 FK가 아니다. 제출은 RegulatoryReport.status=SUBMITTED일 뿐 별도 Submission 모델은 없다.

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
    pms_recall {
        BigAutoField id PK
    }
    pms_customercomplaint ||--o{ pms_capa : "complaint_id"
    auth_user ||--o{ pms_capa : "owner_id"
    pms_capa ||--o{ pms_capaevaluation : "capa_id"
    auth_user ||--o{ pms_capaevaluation : "evaluator_id"
    pms_worktask |o--o| pms_capaevaluation : "followup_id"
    pms_customercomplaint ||--o{ pms_worktask : "complaint_id"
    pms_capa |o--o{ pms_worktask : "capa_id"
    pms_recall |o--o{ pms_worktask : "recall_id"
    auth_user ||--o{ pms_worktask : "assignee_id"
    pms_worktask ||--o{ pms_taskhistory : "task_id"
    auth_user ||--o{ pms_taskhistory : "actor_id"
    pms_customercomplaint ||--o{ pms_attachment : "complaint_id"
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
    pms_customercomplaint ||--o{ pms_worktask : "complaint_id"
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
    pms_customercomplaint ||--o{ pms_regulatoryreport : "complaint_id"
    auth_user ||--o{ pms_regulatoryreport : "author_id"
    auth_user |o--o{ pms_regulatoryreport : "reviewer_id"
    auth_user |o--o{ pms_regulatoryreport : "approved_by_id"
    auth_user |o--o{ pms_regulatoryreporthistory : "actor_id"
    pms_regulatoryreport ||--o{ pms_regulatoryreporthistory : "parent_id"
    pms_customercomplaint ||--o{ pms_reportartifact : "complaint_id"
    auth_user ||--o{ pms_reportartifact : "generated_by_id"
    pms_customercomplaint ||--o{ pms_attachment : "complaint_id"
    auth_user ||--o{ pms_attachment : "uploaded_by_id"
```
