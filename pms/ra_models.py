"""Explicit RA domain records. No jurisdiction-specific legal rules are encoded."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from .history import AppendOnlyRecord

USER=settings.AUTH_USER_MODEL
APPLICABILITY=[('UNVERIFIED','확인 필요'),('APPLIES','적용'),('NOT_APPLICABLE','비적용')]
LIFECYCLE=[(x,label) for x,label in [('DRAFT','초안'),('REVIEW','검토 요청'),('REVIEWED','검토 완료'),('APPROVED','승인'),('EFFECTIVE','시행'),('RETIRED','폐기'),('CANCELLED','취소'),('CLOSED','종결')]]

class RARecord(models.Model):
    title=models.CharField('제목',max_length=240)
    owner=models.ForeignKey(USER,on_delete=models.PROTECT,related_name='+',verbose_name='담당자')
    reviewer=models.ForeignKey(USER,on_delete=models.PROTECT,null=True,blank=True,related_name='+',verbose_name='지정 검토자')
    created_by=models.ForeignKey(USER,on_delete=models.PROTECT,related_name='+')
    reviewed_by=models.ForeignKey(USER,on_delete=models.PROTECT,null=True,blank=True,related_name='+')
    reviewed_at=models.DateTimeField(null=True,blank=True)
    approved_by=models.ForeignKey(USER,on_delete=models.PROTECT,null=True,blank=True,related_name='+')
    approved_at=models.DateTimeField(null=True,blank=True)
    approval_snapshot=models.JSONField(default=dict,blank=True)
    state=models.CharField(max_length=12,choices=LIFECYCLE,default='DRAFT')
    revision=models.PositiveIntegerField(default=1)
    is_example=models.BooleanField('예시 자료',default=False)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        abstract=True
        constraints=[models.CheckConstraint(condition=models.Q(state__in=[x[0] for x in LIFECYCLE]),name='%(class)s_state_valid')]
    def save(self,*args,**kwargs):
        if not getattr(self,'_ra_write',False): raise ValidationError('RA 서비스에서 사유와 버전을 지정해 저장하세요.')
        return super().save(*args,**kwargs)
    def delete(self,*args,**kwargs): raise ValidationError('RA 근거는 삭제하지 않고 취소·폐기 상태로 보존합니다.')
    def __str__(self): return f'{self.title} · {self.pk or "신규"}'

class RegulatoryProfile(RARecord):
    device=models.ForeignKey('pms.MedicalDevice',on_delete=models.PROTECT,related_name='regulatory_profiles')
    jurisdiction=models.CharField('대상 국가·관할',max_length=120)
    organization=models.ForeignKey('pms.BusinessPartner',on_delete=models.PROTECT,verbose_name='적용 조직')
    organization_role=models.CharField('조직 역할',max_length=30,choices=[('MANUFACTURER','제조사'),('IMPORTER','수입사'),('DISTRIBUTOR','유통사'),('OTHER','기타')])
    product_family=models.CharField('제품군',max_length=160,blank=True)
    classification=models.CharField('위험등급',max_length=100,blank=True)
    classification_basis=models.TextField('분류 근거',blank=True)
    intended_use=models.TextField('사용 목적',blank=True)
    authorized_scope=models.TextField('허가된 사용 범위',blank=True)
    applicability=models.CharField(max_length=20,choices=APPLICABILITY,default='UNVERIFIED')
    rationale=models.TextField('판단 사유',blank=True)
    source=models.ForeignKey('pms.RegulationDocument',on_delete=models.PROTECT,null=True,blank=True)
    source_url=models.URLField('공식 원문 출처',max_length=1000,blank=True)
    source_checked_on=models.DateField('원문 확인일',null=True,blank=True)
    source_checked_by=models.ForeignKey(USER,on_delete=models.PROTECT,null=True,blank=True,related_name='+')
    effective_on=models.DateField('기준 시행일',null=True,blank=True)
    next_review_on=models.DateField('다음 검토일',null=True,blank=True)
    class Meta(RARecord.Meta):
        constraints=RARecord.Meta.constraints+[models.UniqueConstraint(fields=['device','jurisdiction','organization','organization_role','is_example'],name='unique_ra_profile')]+[models.CheckConstraint(condition=models.Q(organization_role__in=['MANUFACTURER', 'IMPORTER', 'DISTRIBUTOR', 'OTHER']),name='ra_regulatoryprofile_organization_role_valid'),models.CheckConstraint(condition=models.Q(applicability__in=['UNVERIFIED', 'APPLIES', 'NOT_APPLICABLE']),name='ra_regulatoryprofile_applicability_valid')]

class ScopedRecord(RARecord):
    profile=models.ForeignKey(RegulatoryProfile,on_delete=models.PROTECT,related_name='%(class)s_records')
    evidence=models.ManyToManyField('pms.Attachment',blank=True,related_name='%(class)s_evidence')
    tasks=models.ManyToManyField('pms.WorkTask',blank=True,related_name='%(class)s_tasks')
    class Meta(RARecord.Meta): abstract=True

class RARequirement(ScopedRecord):
    internal_id=models.CharField('내부 요구사항 ID',max_length=80)
    source=models.ForeignKey('pms.RegulationDocument',on_delete=models.PROTECT,null=True,blank=True)
    clause=models.ForeignKey('pms.RegulationChunk',on_delete=models.PROTECT,null=True,blank=True)
    clause_reference=models.CharField('조항',max_length=240,blank=True)
    applicability=models.CharField(max_length=20,choices=APPLICABILITY,default='UNVERIFIED')
    applicability_reason=models.TextField('적용 판단 사유',blank=True)
    activity=models.TextField('필요 활동')
    deliverable=models.TextField('제출물·필요 증빙',blank=True)
    fulfillment=models.CharField('충족 상태',max_length=20,choices=[('UNVERIFIED','확인 필요'),('IN_REVIEW','검토 중'),('MET','충족'),('NOT_MET','미충족'),('NOT_APPLICABLE','비적용')],default='UNVERIFIED')
    due_on=models.DateField('기한',null=True,blank=True)
    review_interval_days=models.PositiveIntegerField('검토 주기(조직 설정)',null=True,blank=True)
    confirmed_on=models.DateField('확인일',null=True,blank=True)
    next_review_on=models.DateField('다음 검토일',null=True,blank=True)
    source_url=models.URLField(max_length=1000,blank=True)
    source_checked_on=models.DateField(null=True,blank=True)
    source_checked_by=models.ForeignKey(USER,on_delete=models.PROTECT,null=True,blank=True,related_name='+')
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.UniqueConstraint(fields=['profile','internal_id'],name='unique_ra_requirement'),models.CheckConstraint(condition=models.Q(fulfillment__in=['UNVERIFIED','IN_REVIEW','MET','NOT_MET','NOT_APPLICABLE']),name='requirement_fulfillment_valid')]+[models.CheckConstraint(condition=models.Q(applicability__in=['UNVERIFIED', 'APPLIES', 'NOT_APPLICABLE']),name='ra_rarequirement_applicability_valid')]
        indexes=[models.Index(fields=['profile','fulfillment','due_on'],name='ra_requirement_due')]

class MarketingAuthorization(ScopedRecord):
    kind=models.CharField('허가·인증·신고 구분',max_length=100)
    number=models.CharField('허가번호',max_length=160,blank=True)
    authority=models.CharField('발급기관',max_length=240,blank=True)
    issued_on=models.DateField('허가일',null=True,blank=True)
    expires_on=models.DateField('유효기간 종료일(없으면 공란)',null=True,blank=True)
    conditions=models.TextField('조건·제한사항',blank=True)
    status=models.CharField('명시적 허가 상태',max_length=20,choices=[('UNKNOWN','미확인'),('APPLICATION','신청'),('SUPPLEMENT','보완'),('APPROVED','승인 기록'),('REJECTED','반려'),('WITHDRAWN','취하'),('EXPIRED','만료'),('SUSPENDED','정지'),('REVOKED','취소')],default='UNKNOWN')
    renewal_prepare_on=models.DateField('갱신 준비 시작일',null=True,blank=True)
    renewal_basis=models.TextField('갱신 기준·판단 사유',blank=True)
    verified_on=models.DateField('기관 정보 확인일',null=True,blank=True)
    verification_source=models.URLField('기관 확인 출처',max_length=1000,blank=True)
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.CheckConstraint(condition=models.Q(expires_on__isnull=True)|models.Q(issued_on__isnull=True)|models.Q(expires_on__gte=models.F('issued_on')),name='authorization_date_order')]+[models.CheckConstraint(condition=models.Q(status__in=['UNKNOWN', 'APPLICATION', 'SUPPLEMENT', 'APPROVED', 'REJECTED', 'WITHDRAWN', 'EXPIRED', 'SUSPENDED', 'REVOKED']),name='ra_marketingauthoriza_status_valid')]
        indexes=[models.Index(fields=['profile','status','expires_on'],name='ra_authorization_expiry')]

class AuthorizationEvent(AppendOnlyRecord):
    authorization=models.ForeignKey(MarketingAuthorization,on_delete=models.PROTECT,related_name='events')
    status=models.CharField(max_length=20)
    reason=models.TextField()
    actor=models.ForeignKey(USER,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    snapshot=models.JSONField()
    class Meta: indexes=[models.Index(fields=['authorization','created_at'],name='ra_authorization_event_time')]

class SubmissionPackage(ScopedRecord):
    product_revision=models.ForeignKey('pms.ProductRevision',on_delete=models.PROTECT,null=True,blank=True,related_name='submission_packages')
    change=models.ForeignKey('pms.ProductChange',on_delete=models.PROTECT,null=True,blank=True,related_name='submission_packages')
    authorization=models.ForeignKey(MarketingAuthorization,on_delete=models.PROTECT,related_name='packages')
    version=models.PositiveIntegerField()
    content_description=models.TextField('제출 패키지 목록·설명')
    receipt_reference=models.CharField('접수번호/증빙 설명',max_length=240,blank=True)
    receipt=models.ForeignKey('pms.Attachment',on_delete=models.PROTECT,null=True,blank=True,related_name='submission_receipts')
    recorded_submitted_on=models.DateField('수동 기록 제출일',null=True,blank=True)
    frozen_snapshot=models.JSONField(default=dict,blank=True)
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.UniqueConstraint(fields=['authorization','version'],name='unique_submission_package'),models.CheckConstraint(condition=models.Q(version__gte=1),name='submission_positive_version')]

class ProductRevision(ScopedRecord):
    version=models.CharField('제품 버전',max_length=80)
    description=models.TextField('제품 구성·버전 설명')
    previous=models.ForeignKey('self',on_delete=models.PROTECT,null=True,blank=True,related_name='successors')
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.UniqueConstraint(fields=['profile','version'],name='unique_product_revision')]

class ControlledDocument(ScopedRecord):
    category=models.CharField('문서 구분',max_length=12,choices=[('SOP','SOP'),('INSTRUCTION','작업지침'),('FORM','양식'),('TECHNICAL','기술문서')])
    number=models.CharField('문서번호',max_length=80)
    version=models.PositiveIntegerField('문서 버전')
    body=models.TextField('본문·파일 설명',blank=True)
    primary_file=models.ForeignKey('pms.Attachment',on_delete=models.PROTECT,null=True,blank=True,related_name='controlled_documents')
    effective_on=models.DateField('시행일',null=True,blank=True)
    next_review_on=models.DateField('정기 검토일',null=True,blank=True)
    change_reason=models.TextField('개정 사유')
    supersedes=models.ForeignKey('self',on_delete=models.PROTECT,null=True,blank=True,related_name='revisions')
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.UniqueConstraint(fields=['profile','number','version'],name='unique_controlled_document'),models.UniqueConstraint(fields=['profile','number'],condition=models.Q(state='EFFECTIVE'),name='one_effective_controlled_doc'),models.CheckConstraint(condition=models.Q(version__gte=1),name='controlled_doc_positive_version')]+[models.CheckConstraint(condition=models.Q(category__in=['SOP', 'INSTRUCTION', 'FORM', 'TECHNICAL']),name='ra_controlleddocument_category_valid')]
        indexes=[models.Index(fields=['profile','state','next_review_on'],name='ra_document_review')]

class ProductChange(ScopedRecord):
    category=models.CharField('변경 구분',max_length=16,choices=[(x,label) for x,label in [('DESIGN','설계'),('MATERIAL','재료'),('SUPPLIER','공급자'),('PROCESS','제조공정'),('SOFTWARE','소프트웨어'),('LABEL','표시')]])
    from_revision=models.ForeignKey(ProductRevision,on_delete=models.PROTECT,related_name='outgoing_changes')
    to_revision=models.ForeignKey(ProductRevision,on_delete=models.PROTECT,related_name='incoming_changes')
    before_content=models.TextField('변경 전')
    after_content=models.TextField('변경 후')
    reason=models.TextField('변경 사유')
    lots=models.ManyToManyField('pms.ProductLot',blank=True,related_name='ra_changes')
    impact_checklist=models.JSONField('영향 검토(허가·위험·검증·라벨·교육·PMS)',default=dict,blank=True)
    submission_decision=models.CharField('추가 제출 판단',max_length=16,choices=[('UNVERIFIED','확인 필요'),('REQUIRED','필요'),('NOT_REQUIRED','불필요')],default='UNVERIFIED')
    decision_basis=models.TextField('제출 판단 근거',blank=True)
    authorization=models.ForeignKey(MarketingAuthorization,on_delete=models.PROTECT,null=True,blank=True,related_name='changes')
    documents=models.ManyToManyField(ControlledDocument,blank=True,related_name='product_changes')
    implemented_on=models.DateField('시행일',null=True,blank=True)
    implementation_confirmation=models.TextField('시행 확인 근거',blank=True)

    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.CheckConstraint(condition=models.Q(category__in=['DESIGN', 'MATERIAL', 'SUPPLIER', 'PROCESS', 'SOFTWARE', 'LABEL']),name='ra_productchange_category_valid'),models.CheckConstraint(condition=models.Q(submission_decision__in=['UNVERIFIED', 'REQUIRED', 'NOT_REQUIRED']),name='ra_productchange_submission_decisi_valid')]

class LabelVersion(ScopedRecord):
    artifact_type=models.CharField('표시 자료',max_length=8,choices=[('LABEL','라벨'),('IFU','사용설명서')])
    language=models.CharField('언어',max_length=60)
    version=models.PositiveIntegerField('표시 버전')
    document=models.ForeignKey(ControlledDocument,on_delete=models.PROTECT,related_name='labels')
    product_revision=models.ForeignKey(ProductRevision,on_delete=models.PROTECT,related_name='labels')
    authorization=models.ForeignKey(MarketingAuthorization,on_delete=models.PROTECT,null=True,blank=True,related_name='labels')
    change=models.ForeignKey(ProductChange,on_delete=models.PROTECT,null=True,blank=True,related_name='labels')
    udi=models.ForeignKey('pms.UDI',on_delete=models.PROTECT,null=True,blank=True,related_name='labels')
    review_checklist=models.JSONField('UDI·모델·사용목적·경고·주의 검토',default=dict,blank=True)
    translation_reviewer=models.ForeignKey(USER,on_delete=models.PROTECT,null=True,blank=True,related_name='+')
    translation_reviewed_on=models.DateField(null=True,blank=True)
    translation_notes=models.TextField('번역 검토 의견',blank=True)
    effective_on=models.DateField('시행일',null=True,blank=True)
    lots=models.ManyToManyField('pms.ProductLot',blank=True,related_name='label_versions')
    previous=models.ForeignKey('self',on_delete=models.PROTECT,null=True,blank=True,related_name='successors')
    safety_action=models.ForeignKey('pms.FieldSafetyAction',on_delete=models.PROTECT,null=True,blank=True,related_name='label_changes')
    safety_change_reason=models.TextField('안전조치로 변경된 문구·사유',blank=True)
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.UniqueConstraint(fields=['profile','artifact_type','language','version'],name='unique_label_version'),models.UniqueConstraint(fields=['profile','artifact_type','language'],condition=models.Q(state='EFFECTIVE'),name='one_effective_label'),models.CheckConstraint(condition=models.Q(version__gte=1),name='label_positive_version')]+[models.CheckConstraint(condition=models.Q(artifact_type__in=['LABEL', 'IFU']),name='ra_labelversion_artifact_type_valid')]

class RiskCriteria(ScopedRecord):
    version=models.PositiveIntegerField('수용 기준 버전')
    estimation_method=models.TextField('제품별 위험 추정 방법')
    acceptance_criteria=models.TextField('조직 승인 수용 기준')
    basis=models.TextField('기준 근거·적용 범위')
    document=models.ForeignKey(ControlledDocument,on_delete=models.PROTECT,null=True,blank=True,related_name='risk_criteria')
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.UniqueConstraint(fields=['profile','version'],name='unique_risk_criteria_version')]+[models.CheckConstraint(condition=models.Q(version__gte=1),name="riskcriteria_positive_version")]

class ProductRisk(ScopedRecord):
    criteria=models.ForeignKey(RiskCriteria,on_delete=models.PROTECT,related_name='risks')
    document=models.ForeignKey(ControlledDocument,on_delete=models.PROTECT,null=True,blank=True,related_name='product_risks')
    hazard=models.TextField('위해요인')
    hazardous_situation=models.TextField('위해상황')
    harm=models.TextField('위해')
    estimate=models.TextField('위험 추정과 근거')
    controls=models.TextField('위험통제 조치',blank=True)
    verification=models.TextField('통제 검증 근거',blank=True)
    residual_decision=models.CharField('잔여위험 판단',max_length=20,choices=[('UNVERIFIED','확인 필요'),('ACCEPTABLE','수용 가능 판단'),('NOT_ACCEPTABLE','수용 불가 판단')],default='UNVERIFIED')
    residual_rationale=models.TextField('잔여위험 검토 근거',blank=True)
    benefit_risk_rationale=models.TextField('편익·위험 담당자 판단',blank=True)
    next_review_on=models.DateField(null=True,blank=True)
    complaints=models.ManyToManyField('pms.CustomerComplaint',blank=True,related_name='product_risks')
    adverse_events=models.ManyToManyField('pms.AdverseEvent',blank=True,related_name='product_risks')
    signals=models.ManyToManyField('pms.SafetySignal',blank=True,related_name='product_risks')
    capas=models.ManyToManyField('pms.CAPA',blank=True,related_name='product_risks')

    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.CheckConstraint(condition=models.Q(residual_decision__in=['UNVERIFIED', 'ACCEPTABLE', 'NOT_ACCEPTABLE']),name='ra_productrisk_residual_decision_valid')]

class SafetyInformation(ScopedRecord):
    source_url=models.URLField('원문 출처',max_length=1000)
    source_identifier=models.CharField('외부 정보 식별자',max_length=240)
    collected_on=models.DateField('수집일',default=timezone.localdate)
    original=models.ForeignKey('pms.Attachment',on_delete=models.PROTECT,null=True,blank=True,related_name='external_safety_information')
    relevance=models.CharField('제품 연관성',max_length=16,choices=[('UNVERIFIED','확인 필요'),('RELATED','관련'),('UNRELATED','비관련')],default='UNVERIFIED')
    relevance_reason=models.TextField('제품 연관성 검토 근거',blank=True)
    reporting_decision=models.CharField('보고 필요 판단',max_length=16,choices=[('UNVERIFIED','확인 필요'),('REQUIRED','필요'),('NOT_REQUIRED','불필요')],default='UNVERIFIED')
    reporting_basis=models.TextField('보고 판단 근거',blank=True)
    report=models.ForeignKey('pms.RegulatoryReport',on_delete=models.PROTECT,null=True,blank=True,related_name='safety_information')
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.UniqueConstraint(fields=['profile','source_url','source_identifier'],name='unique_external_safety_source')]+[models.CheckConstraint(condition=models.Q(relevance__in=['UNVERIFIED', 'RELATED', 'UNRELATED']),name='ra_safetyinformation_relevance_valid'),models.CheckConstraint(condition=models.Q(reporting_decision__in=['UNVERIFIED', 'REQUIRED', 'NOT_REQUIRED']),name='ra_safetyinformation_reporting_decisio_valid')]

class FieldSafetyAction(ScopedRecord):
    action_type=models.CharField('현장 조치 구분',max_length=16,choices=[('NOTICE','고객 안내'),('CORRECTION','현장 수정'),('RECALL','회수')])
    information=models.ForeignKey(SafetyInformation,on_delete=models.PROTECT,null=True,blank=True,related_name='actions')
    complaint=models.ForeignKey('pms.CustomerComplaint',on_delete=models.PROTECT,null=True,blank=True,related_name='field_actions')
    signal=models.ForeignKey('pms.SafetySignal',on_delete=models.PROTECT,null=True,blank=True,related_name='field_actions')
    capa=models.ForeignKey('pms.CAPA',on_delete=models.PROTECT,null=True,blank=True,related_name='field_actions')
    recall=models.OneToOneField('pms.Recall',on_delete=models.PROTECT,null=True,blank=True,related_name='field_action')
    notice_document=models.ForeignKey(ControlledDocument,on_delete=models.PROTECT,related_name='field_actions')
    rationale=models.TextField('조치 필요 근거')
    effectiveness_criteria=models.TextField('효과 확인 기준',blank=True)
    closure_rationale=models.TextField('종결 검토 근거',blank=True)
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.CheckConstraint(condition=models.Q(action_type='RECALL',recall__isnull=False)|(~models.Q(action_type='RECALL')&models.Q(recall__isnull=True)),name='field_action_recall_context')]+[models.CheckConstraint(condition=models.Q(action_type__in=['NOTICE', 'CORRECTION', 'RECALL']),name='ra_fieldsafetyaction_action_type_valid')]

class FieldActionRecipient(ScopedRecord):
    action=models.ForeignKey(FieldSafetyAction,on_delete=models.PROTECT,related_name='recipients')
    partner=models.ForeignKey('pms.BusinessPartner',on_delete=models.PROTECT,related_name='field_recipients')
    lot=models.ForeignKey('pms.ProductLot',on_delete=models.PROTECT)
    unit=models.CharField('단위',max_length=20,default='개')
    target_quantity=models.PositiveIntegerField('조치 대상 수량')
    completed_quantity=models.PositiveIntegerField('조치 완료 누계',default=0)
    notified_on=models.DateField('수동 통보 기록일',null=True,blank=True)
    acknowledged_on=models.DateField('수신 확인일',null=True,blank=True)
    completed_on=models.DateField('조치 완료 확인일',null=True,blank=True)
    outcome=models.TextField('완료 증빙·미응답/미조치 사유',blank=True)
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.UniqueConstraint(fields=['action','partner','lot','unit'],name='unique_field_action_recipient'),models.CheckConstraint(condition=models.Q(target_quantity__gte=1,completed_quantity__lte=models.F('target_quantity')),name='field_recipient_quantity')]

class FieldActionContact(AppendOnlyRecord):
    recipient=models.ForeignKey(FieldActionRecipient,on_delete=models.PROTECT,related_name='contacts')
    actor=models.ForeignKey(USER,on_delete=models.PROTECT)
    contacted_at=models.DateTimeField(default=timezone.now)
    method=models.CharField(max_length=120)
    note=models.TextField()
    evidence=models.ForeignKey('pms.Attachment',on_delete=models.PROTECT,null=True,blank=True,related_name='field_contacts')

class FieldActionEvaluation(AppendOnlyRecord):
    action=models.ForeignKey(FieldSafetyAction,on_delete=models.PROTECT,related_name='evaluations')
    actor=models.ForeignKey(USER,on_delete=models.PROTECT)
    evaluated_at=models.DateTimeField(auto_now_add=True)
    verdict=models.CharField(max_length=12,choices=[('EFFECTIVE','효과 확인'),('INEFFECTIVE','미흡')])
    rationale=models.TextField()
    evidence=models.ForeignKey('pms.Attachment',on_delete=models.PROTECT,related_name='field_evaluations')
    snapshot=models.JSONField()

    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(verdict__in=['EFFECTIVE', 'INEFFECTIVE']),name='ra_fieldactionevaluat_verdict_valid')]

class SupplierRecord(ScopedRecord):
    partner=models.ForeignKey('pms.BusinessPartner',on_delete=models.PROTECT,related_name='ra_supplier_records')
    supplier_type=models.CharField('유형',max_length=20,choices=[('SUPPLIER','공급자'),('SITE','제조소'),('CONTRACTOR','위탁업체')])
    site_reference=models.CharField('제조소 식별·소재지',max_length=240,blank=True)
    process_service=models.TextField('관련 제품·공정·서비스')
    evaluation_criteria=models.TextField('조직 평가 기준·주기 판단 근거')
    criteria_document=models.ForeignKey(ControlledDocument,on_delete=models.PROTECT,null=True,blank=True,related_name='supplier_criteria')
    next_review_on=models.DateField('다음 검토일(조직 판단)',null=True,blank=True)
    capas=models.ManyToManyField('pms.CAPA',blank=True,related_name='supplier_records')
    nonconformity_reference=models.TextField('관련 부적합 기록 참조',blank=True)

    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.CheckConstraint(condition=models.Q(supplier_type__in=['SUPPLIER', 'SITE', 'CONTRACTOR']),name='ra_supplierrecord_supplier_type_valid')]

class SupplierMaterial(ScopedRecord):
    supplier=models.ForeignKey(SupplierRecord,on_delete=models.PROTECT,related_name='materials')
    category=models.CharField('자료 구분',max_length=20,choices=[('CERTIFICATE','인증서'),('CONTRACT','계약'),('QUALITY_AGREEMENT','품질협약'),('OTHER','기타')])
    version=models.CharField('자료 버전',max_length=80)
    issued_on=models.DateField(null=True,blank=True)
    expires_on=models.DateField(null=True,blank=True)
    deficiencies=models.TextField('미비 자료·보완사항',blank=True)
    next_review_on=models.DateField('다음 검토일',null=True,blank=True)
    change_notice=models.TextField('변경 통보',blank=True)
    impact_review=models.TextField('변경 영향 검토 근거',blank=True)
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.UniqueConstraint(fields=['supplier','category','version'],name='unique_supplier_material'),models.CheckConstraint(condition=models.Q(expires_on__isnull=True)|models.Q(issued_on__isnull=True)|models.Q(expires_on__gte=models.F('issued_on')),name='supplier_material_date_order')]+[models.CheckConstraint(condition=models.Q(category__in=['CERTIFICATE', 'CONTRACT', 'QUALITY_AGREEMENT', 'OTHER']),name='ra_suppliermaterial_category_valid')]

class TrainingRequirement(ScopedRecord):
    document=models.ForeignKey(ControlledDocument,on_delete=models.PROTECT,related_name='training_requirements')
    required_role=models.CharField('대상 역할',max_length=10,choices=[('STAFF','직원'),('RA_QA','RA/QA'),('ADMIN','관리자')])
    due_on=models.DateField('교육 기한',null=True,blank=True)
    effectiveness_method=models.TextField('효과 확인 방법')
    enforce_ra_approval=models.BooleanField('명시적 제한: 미수료자 신규 RA 최종 승인 차단',default=False)
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.UniqueConstraint(fields=['profile','document','required_role'],name='unique_role_document_training')]+[models.CheckConstraint(condition=models.Q(required_role__in=['STAFF', 'RA_QA', 'ADMIN']),name='ra_trainingrequiremen_required_role_valid')]

class TrainingAssignment(ScopedRecord):
    attempt=models.PositiveIntegerField("교육 시도 번호",default=1)
    requirement=models.ForeignKey(TrainingRequirement,on_delete=models.PROTECT,related_name='assignments')
    trainee=models.ForeignKey(USER,on_delete=models.PROTECT,related_name='ra_training')
    due_on=models.DateField('교육 기한',null=True,blank=True)
    completed_on=models.DateField('수료일',null=True,blank=True)
    completion_evidence=models.ForeignKey('pms.Attachment',on_delete=models.PROTECT,null=True,blank=True,related_name='training_completions')
    training_status=models.CharField('교육 상태',max_length=20,choices=[('PENDING','미수료'),('COMPLETED','수료 확인'),('RETRAIN','재교육'),('NEEDS_REVIEW','역할·개정 영향 검토'),('INACTIVE','비활성 대상자')],default='PENDING')
    effectiveness=models.CharField('효과 판정',max_length=12,choices=[('UNVERIFIED','확인 필요'),('PASS','적합'),('FAIL','미흡')],default='UNVERIFIED')
    effectiveness_rationale=models.TextField('교육·자격 효과 확인 근거',blank=True)
    retraining_of=models.ForeignKey('self',on_delete=models.PROTECT,null=True,blank=True,related_name='retraining')
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.CheckConstraint(condition=models.Q(attempt__gte=1),name="training_positive_attempt"),models.UniqueConstraint(fields=['requirement','trainee','attempt'],name='unique_training_assignment'),models.CheckConstraint(condition=~models.Q(training_status='COMPLETED')|(models.Q(completed_on__isnull=False,completion_evidence__isnull=False,effectiveness='PASS')),name='training_completion_evidence')]+[models.CheckConstraint(condition=models.Q(training_status__in=['PENDING', 'COMPLETED', 'RETRAIN', 'NEEDS_REVIEW', 'INACTIVE']),name='ra_trainingassignment_training_status_valid'),models.CheckConstraint(condition=models.Q(effectiveness__in=['UNVERIFIED', 'PASS', 'FAIL']),name='ra_trainingassignment_effectiveness_valid')]
        indexes=[models.Index(fields=['trainee','training_status','due_on'],name='ra_training_due')]

class AuditPlan(ScopedRecord):
    audit_type=models.CharField('감사 유형',max_length=12,choices=[('INTERNAL','내부 감사'),('EXTERNAL','외부 실사')])
    scheduled_on=models.DateField('일정')
    scope=models.TextField('감사·실사 범위')
    criteria=models.TextField('검토 기준·근거')
    checklist=models.JSONField('점검 항목',default=dict,blank=True)
    closure_rationale=models.TextField('감사 종결 근거',blank=True)

    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.CheckConstraint(condition=models.Q(audit_type__in=['INTERNAL', 'EXTERNAL']),name='ra_auditplan_audit_type_valid')]

class AuditFinding(ScopedRecord):
    audit=models.ForeignKey(AuditPlan,on_delete=models.PROTECT,related_name='findings')
    observation=models.TextField('관찰·지적 내용')
    classification=models.CharField('분류',max_length=100)
    classification_basis=models.TextField('분류 근거')
    due_on=models.DateField('답변 기한',null=True,blank=True)
    response=models.TextField('답변·수정 내용',blank=True)
    capa=models.ForeignKey('pms.CAPA',on_delete=models.PROTECT,null=True,blank=True,related_name='audit_findings')
    effectiveness=models.CharField('효과 확인',max_length=12,choices=[('UNVERIFIED','확인 필요'),('PASS','적합'),('FAIL','미흡')],default='UNVERIFIED')
    effectiveness_rationale=models.TextField('효과 검토·종결 근거',blank=True)

    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.CheckConstraint(condition=models.Q(effectiveness__in=['UNVERIFIED', 'PASS', 'FAIL']),name='ra_auditfinding_effectiveness_valid')]

class AuditPackage(ScopedRecord):
    audit=models.ForeignKey(AuditPlan,on_delete=models.PROTECT,related_name='packages')
    version=models.PositiveIntegerField('자료 패키지 버전')
    description=models.TextField('자료 목록·제출 범위')
    receipt_reference=models.CharField('수동 제출·접수 증빙 참조',max_length=240,blank=True)
    frozen_snapshot=models.JSONField(default=dict,blank=True)
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.UniqueConstraint(fields=['audit','version'],name='unique_audit_package')]+[models.CheckConstraint(condition=models.Q(version__gte=1),name="auditpackage_positive_version")]

class ManagementReview(ScopedRecord):
    period_start=models.DateField('집계 기간 시작')
    period_end=models.DateField('집계 기간 종료')
    meeting_on=models.DateField('검토 회의일',null=True,blank=True)
    unresolved_risks=models.TextField('미해결 위험·결정 필요 사항',blank=True)
    meeting_notes=models.TextField('회의 검토 의견·결정',blank=True)
    management_snapshot=models.JSONField(default=dict,blank=True)
    captured_at=models.DateTimeField(null=True,blank=True)
    pms_report=models.ForeignKey('pms.ReportArtifact',on_delete=models.PROTECT,null=True,blank=True,related_name='management_reviews')
    class Meta(ScopedRecord.Meta):
        constraints=ScopedRecord.Meta.constraints+[models.CheckConstraint(condition=models.Q(period_end__gte=models.F('period_start')),name='management_period_order')]

class ManagementDecision(ScopedRecord):
    review=models.ForeignKey(ManagementReview,on_delete=models.PROTECT,related_name='decisions')
    decision=models.TextField('회의 결정·후속 활동')
    rationale=models.TextField('결정 근거')
    due_on=models.DateField('후속 기한',null=True,blank=True)
    completed_on=models.DateField('완료 확인일',null=True,blank=True)
    outcome=models.TextField('후속 결과',blank=True)

class RetentionPolicy(RARecord):
    organization=models.ForeignKey('pms.BusinessPartner',on_delete=models.PROTECT,related_name='retention_policies')
    record_category=models.CharField('보존 대상 범주',max_length=100)
    legal_source=models.ForeignKey('pms.RegulationDocument',on_delete=models.PROTECT,null=True,blank=True,related_name='retention_policies')
    source_url=models.URLField('근거 URL',max_length=1000,blank=True)
    checked_on=models.DateField('근거 확인일',null=True,blank=True)
    retention_basis=models.TextField('보존 기간·기산점·파기 판단의 조직 근거')
    duration_days=models.PositiveIntegerField('조직이 확인한 보존 일수(미확인은 공란)',null=True,blank=True)
    disposal_procedure=models.TextField('파기 검토·승인 절차',blank=True)
    automatic_deletion=models.BooleanField(default=False,editable=False)
    class Meta(RARecord.Meta):
        constraints=RARecord.Meta.constraints+[models.CheckConstraint(condition=models.Q(automatic_deletion=False),name='ra_no_automatic_deletion')]


# All application writes use services. Signals also protect direct relation/deletion paths.
from django.db.models.signals import pre_delete,m2m_changed
from django.dispatch import receiver

@receiver(pre_delete)
def preserve_ra_record(sender,instance,**kwargs):
    if isinstance(instance,(RARecord,AuthorizationEvent,FieldActionContact,FieldActionEvaluation)):
        raise ValidationError('RA 근거·행위 이력은 삭제할 수 없습니다.')

@receiver(m2m_changed)
def guard_ra_links(sender,instance,action,reverse,pk_set=None,**kwargs):
    parent=getattr(sender._meta,'auto_created',False)
    if not isinstance(parent,type) or not issubclass(parent,RARecord) or not action.startswith('pre_'): return
    if reverse or not getattr(instance,'_ra_link_write',False):
        raise ValidationError('RA 관계 변경은 검증 서비스로만 처리하세요.')
