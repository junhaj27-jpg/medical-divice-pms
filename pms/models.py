import uuid
from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.utils import timezone
from .history import AppendOnlyRecord
from .market_models import LANGUAGES

class TimeStamped(models.Model):
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: abstract=True
    def clean(self):
        from .model_integrity import validate_relations
        validate_relations(self)

    def save(self,*args,**kwargs):
        # Writers of approval inputs share the case lock used by approval and transitions.
        with transaction.atomic():
            if getattr(self,"ra_profile_id",None): RegulatoryProfile.objects.select_for_update().get(pk=self.ra_profile_id)
            case_id=self.pk if type(self).__name__=='CustomerComplaint' else getattr(self,'complaint_id',None)
            if not case_id and type(self).__name__ in ('RecallTarget','RecallRecipient') and self.recall_id:
                case_id=Recall.objects.values_list('complaint_id',flat=True).get(pk=self.recall_id)
            case_ids={case_id} if case_id else set()
            if self.pk and hasattr(self,'complaint_id'):
                old_id=type(self).objects.filter(pk=self.pk).values_list('complaint_id',flat=True).first()
                if old_id: case_ids.add(old_id)
            for locked_id in sorted(case_ids): CustomerComplaint.objects.select_for_update().get(pk=locked_id)
            if type(self).__name__ == 'Recall' and self.pk:
                Recall.objects.select_for_update().get(pk=self.pk)
            if type(self).__name__ in ('RecallTarget', 'RecallRecipient'):
                self.recall=Recall.objects.select_for_update().get(pk=self.recall_id)
            if isinstance(self, SoftwareRelease) and self.device_id:
                self.device = MedicalDevice.objects.select_for_update().get(pk=self.device_id)
            if isinstance(self, MedicalDevice) and self.pk:
                MedicalDevice.objects.select_for_update().get(pk=self.pk)
            from .model_integrity import validate_relations
            validate_relations(self)
            history_model = {'RiskAssessment': 'RiskAssessmentHistory', 'RegulatoryReport': 'RegulatoryReportHistory'}.get(type(self).__name__)
            before = type(self).objects.filter(pk=self.pk).values().first() if self.pk and history_model else None
            result = super().save(*args,**kwargs)
            if history_model:
                from django.core.serializers.json import DjangoJSONEncoder
                import json
                after = type(self).objects.filter(pk=self.pk).values().get()
                comparable=lambda row: {k:v for k,v in (row or {}).items() if k not in ('created_at','updated_at')}
                if comparable(before) != comparable(after):
                    globals()[history_model].objects.create(parent=self, actor=getattr(self, '_history_actor', None),
                        reason=getattr(self, '_history_reason', '') or getattr(self, 'rationale', ''),
                        source='APPLICATION' if getattr(self, '_history_actor', None) else 'DIRECT_MODEL',
                        before=json.loads(json.dumps(before or {}, cls=DjangoJSONEncoder)),
                        after=json.loads(json.dumps(after, cls=DjangoJSONEncoder)))
            return result

class Profile(models.Model):
    class Role(models.TextChoices): STAFF="STAFF","직원"; RA_QA="RA_QA","RA/QA"; ADMIN="ADMIN","관리자"
    user=models.OneToOneField(User,on_delete=models.CASCADE,related_name="profile"); role=models.CharField(max_length=10,choices=Role.choices,default=Role.STAFF)
    timezone_name=models.CharField("시간대",max_length=64,default="Asia/Seoul")
    ui_language=models.CharField(max_length=8,choices=LANGUAGES,default="ko-KR")
    def __str__(self): return f"{self.user.username} ({self.role})"

class Manufacturer(TimeStamped):
    name=models.CharField(max_length=200,unique=True); country=models.CharField(max_length=100,blank=True); contact_email=models.EmailField(blank=True)
    def __str__(self): return self.name
class MedicalDevice(TimeStamped):
    class ProductType(models.TextChoices):
        HARDWARE = "HARDWARE", "하드웨어"
        SOFTWARE = "SOFTWARE", "소프트웨어"

    product_type = models.CharField("제품 유형", max_length=12, choices=ProductType.choices, blank=True)

    manufacturer=models.ForeignKey(Manufacturer,on_delete=models.PROTECT,related_name="devices"); name=models.CharField(max_length=200); model_number=models.CharField(max_length=100); risk_class=models.CharField(max_length=20,blank=True); active=models.BooleanField(default=True)
    class Meta: unique_together=("manufacturer","model_number")
    def __str__(self): return f"{self.name} ({self.model_number})"
class SoftwareRelease(TimeStamped):
    device = models.ForeignKey(MedicalDevice, on_delete=models.PROTECT, related_name="software_releases")
    version = models.CharField("버전", max_length=80)
    released_on = models.DateField("출시일")

    class Meta:
        ordering = ("-released_on", "version", "pk")
        constraints = [models.UniqueConstraint(fields=("device", "version"), name="software_release_device_version_unique")]

    def __str__(self):
        return self.version


class UDI(TimeStamped):
    device=models.ForeignKey(MedicalDevice,on_delete=models.CASCADE,related_name="udis"); device_identifier=models.CharField(max_length=100,unique=True)
    def __str__(self): return self.device_identifier
class ProductLot(TimeStamped):
    device=models.ForeignKey(MedicalDevice,on_delete=models.CASCADE,related_name="lots"); udi=models.ForeignKey(UDI,on_delete=models.PROTECT,related_name="lots"); lot_number=models.CharField(max_length=100); serial_number=models.CharField(max_length=100,blank=True); manufactured_on=models.DateField(null=True,blank=True); expires_on=models.DateField(null=True,blank=True); distributed_quantity=models.PositiveIntegerField(default=0)
    class Meta: unique_together=("udi","lot_number","serial_number")
    def clean(self):
        super().clean()
        if self.udi_id and self.device_id and self.udi.device_id!=self.device_id: raise ValidationError("UDI는 선택한 의료기기에 속해야 합니다.")
    def __str__(self): return f"{self.lot_number} / {self.serial_number or '-'}"

class CustomerComplaint(TimeStamped):
    intake_release = models.ForeignKey(SoftwareRelease, verbose_name="접수 버전", on_delete=models.PROTECT, null=True, blank=True, related_name="intake_cases")
    affected_releases = models.ManyToManyField(SoftwareRelease, verbose_name="영향 버전", blank=True, related_name="affected_cases")
    impact_rationale = models.TextField("영향 범위 검토 근거", blank=True)

    is_example=models.BooleanField("테스트용 사건",default=False)
    class Status(models.TextChoices): RECEIVED="RECEIVED","접수"; REVIEW="REVIEW","RA/QA 검토"; AE_DECISION="AE_DECISION","이상사례 판단"; RISK="RISK","위험평가"; CAPA_DECISION="CAPA_DECISION","CAPA 판단"; REPORT_REVIEW="REPORT_REVIEW","규제보고 검토"; RECALL_REVIEW="RECALL_REVIEW","리콜 검토"; APPROVAL="APPROVAL","관리자 승인"; ACTION_COMPLETE="ACTION_COMPLETE","조치 완료"; CLOSED="CLOSED","종료"
    device=models.ForeignKey(MedicalDevice,on_delete=models.PROTECT,related_name="complaints"); udi=models.ForeignKey(UDI,on_delete=models.PROTECT); lot=models.ForeignKey(ProductLot,on_delete=models.PROTECT,null=True,blank=True,related_name="complaints"); serial_number=models.CharField(max_length=100,blank=True); complaint_type=models.CharField(max_length=50,db_index=True); title=models.CharField(max_length=200); description=models.TextField(); occurred_on=models.DateField(); reported_on=models.DateField(default=timezone.localdate); reporter=models.ForeignKey(User,on_delete=models.PROTECT,related_name="reported_complaints"); assignee=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="assigned_complaints"); status=models.CharField(max_length=20,choices=Status.choices,default=Status.RECEIVED); due_date=models.DateField(null=True,blank=True); version=models.PositiveIntegerField(default=1)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(status__in=['RECEIVED', 'REVIEW', 'AE_DECISION', 'RISK', 'CAPA_DECISION', 'REPORT_REVIEW', 'RECALL_REVIEW', 'APPROVAL', 'ACTION_COMPLETE', 'CLOSED']),name="customercomplaint_status_valid")]
        ordering=["-created_at"]
        indexes=[models.Index(fields=["reported_on","device","lot"],name="complaint_period_product"),models.Index(fields=["reporter","reported_on"],name="complaint_owner_period")]
    def __str__(self): return f"CMP-{self.pk or 'NEW'} {self.title}"
@receiver(m2m_changed, sender=CustomerComplaint.affected_releases.through)
def validate_affected_releases(sender, instance, action, reverse, pk_set, using, **kwargs):
    if action not in ("pre_add", "pre_remove", "pre_clear"):
        return
    cases = CustomerComplaint.objects.using(using).select_for_update().order_by("pk")
    if reverse:
        cases = cases.filter(pk__in=pk_set) if pk_set is not None else cases.filter(affected_releases=instance)
        for case in cases:
            if action == "pre_add" and case.device_id != instance.device_id:
                raise ValidationError("영향 버전은 사건 제품에 속해야 합니다.")
    else:
        case = cases.get(pk=instance.pk)
        if action == "pre_add" and SoftwareRelease.objects.using(using).filter(pk__in=pk_set).exclude(device_id=case.device_id).exists():
            raise ValidationError("영향 버전은 사건 제품에 속해야 합니다.")


class PatientAnonymousInfo(TimeStamped):
    complaint=models.OneToOneField(CustomerComplaint,on_delete=models.PROTECT,related_name="patient_info"); anonymous_code=models.CharField(max_length=64,unique=True); age_band=models.CharField(max_length=20,blank=True); sex=models.CharField(max_length=20,blank=True); notes=models.TextField(blank=True)
    def clean(self):
        super().clean()
        forbidden=("name","phone","resident","이름","전화","주민")
        if any(x in self.notes.lower() for x in forbidden): raise ValidationError("직접 식별정보는 저장할 수 없습니다.")
class AdverseEvent(TimeStamped):
    complaint=models.OneToOneField(CustomerComplaint,on_delete=models.PROTECT,related_name="adverse_event"); patient=models.ForeignKey(PatientAnonymousInfo,on_delete=models.PROTECT,null=True,blank=True); event_type=models.CharField(max_length=50); outcome=models.CharField(max_length=100); serious=models.BooleanField(default=False); narrative=models.TextField()
class RiskAssessment(TimeStamped):
    complaint=models.OneToOneField(CustomerComplaint,on_delete=models.PROTECT,related_name="risk_assessment"); severity=models.PositiveSmallIntegerField(validators=[MinValueValidator(1),MaxValueValidator(5)]); probability=models.PositiveSmallIntegerField(validators=[MinValueValidator(1),MaxValueValidator(5)]); score=models.PositiveSmallIntegerField(default=1,editable=False); level=models.CharField(max_length=10,editable=False); capa_review_required=models.BooleanField(default=False,editable=False); rationale=models.TextField(blank=True); assessed_by=models.ForeignKey(User,on_delete=models.PROTECT)
    def save(self,*a,**kw):
        self.score=self.severity*self.probability
        self.level="LOW" if self.score<=4 else "MEDIUM" if self.score<=9 else "HIGH" if self.score<=16 else "CRITICAL"
        self.capa_review_required=self.score>=10
        if kw.get('update_fields') is not None:
            kw['update_fields']=set(kw['update_fields'])|{'score','level','capa_review_required'}
        super().save(*a,**kw)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(severity__range=(1,5),probability__range=(1,5)),name="risk_values_range"),models.CheckConstraint(condition=models.Q(score=models.F("severity")*models.F("probability")),name="risk_score_product")]

class CAPA(TimeStamped):
    class Status(models.TextChoices): OPEN="OPEN","개시"; INVESTIGATION="INVESTIGATION","조사"; IMPLEMENTATION="IMPLEMENTATION","실행"; EFFECTIVENESS="EFFECTIVENESS","효과확인"; CLOSED="CLOSED","종료"
    complaint=models.ForeignKey(CustomerComplaint,on_delete=models.PROTECT,related_name="capas"); title=models.CharField(max_length=200); root_cause=models.TextField(blank=True); corrective_action=models.TextField(); preventive_action=models.TextField(blank=True); owner=models.ForeignKey(User,on_delete=models.PROTECT); due_date=models.DateField(); status=models.CharField(max_length=20,choices=Status.choices,default=Status.OPEN)
    action_result=models.TextField("조치 결과",blank=True)
    evaluation_criteria=models.TextField("평가 기준",blank=True)
    evaluation_due=models.DateField("평가 예정일",null=True,blank=True)
    def clean(self):
        super().clean()
        if self.status == self.Status.CLOSED:
            latest=self.evaluations.order_by("-created_at","-pk").first() if self.pk else None
            if not self.action_result.strip() or not self.evaluation_criteria.strip() or not self.evaluation_due or not latest or latest.verdict != "PASS" or latest.action_result != self.action_result or latest.criteria != self.evaluation_criteria or latest.scheduled_on != self.evaluation_due:
                raise ValidationError("조치 결과·평가 기준·예정일과 적합 효과성 평가가 있어야 종결할 수 있습니다.")
    def save(self,*args,**kwargs):
        with transaction.atomic():
            if self.complaint_id: CustomerComplaint.objects.select_for_update().get(pk=self.complaint_id)
            if self.pk: type(self).objects.select_for_update().get(pk=self.pk)
            self.clean(); return super().save(*args,**kwargs)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(status__in=['OPEN', 'INVESTIGATION', 'IMPLEMENTATION', 'EFFECTIVENESS', 'CLOSED']),name="capa_status_valid")]

class Recall(TimeStamped):
    class Approval(models.TextChoices): DRAFT="DRAFT","작성"; PENDING="PENDING","승인대기"; APPROVED="APPROVED","승인"; REJECTED="REJECTED","반려"
    class Progress(models.TextChoices): PLANNED="PLANNED","계획"; ACTIVE="ACTIVE","진행"; COMPLETED="COMPLETED","완료"; CLOSED="CLOSED","종료"
    complaint=models.ForeignKey(CustomerComplaint,on_delete=models.PROTECT,null=True,blank=True,related_name="recalls"); title=models.CharField(max_length=200); reason=models.TextField(); risk_level=models.CharField(max_length=10); device=models.ForeignKey(MedicalDevice,on_delete=models.PROTECT,related_name="recalls"); distributed_quantity=models.PositiveIntegerField(); target_quantity=models.PositiveIntegerField(); recovered_quantity=models.PositiveIntegerField(default=0); start_date=models.DateField(); expected_end_date=models.DateField(); owner=models.ForeignKey(User,on_delete=models.PROTECT); approval_status=models.CharField(max_length=10,choices=Approval.choices,default=Approval.DRAFT); decision_reason=models.TextField(blank=True); progress_status=models.CharField(max_length=10,choices=Progress.choices,default=Progress.PLANNED); closure_report=models.TextField(blank=True)
    def clean(self):
        super().clean()
        if self.target_quantity>self.distributed_quantity: raise ValidationError("회수 목표 수량은 유통 수량을 초과할 수 없습니다.")
        if self.recovered_quantity>self.target_quantity: raise ValidationError("실제 회수 수량은 목표 수량을 초과할 수 없습니다.")
    @property
    def recovery_rate(self): return round(self.recovered_quantity/self.target_quantity*100,1) if self.target_quantity else 0
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(target_quantity__lte=models.F("distributed_quantity"),recovered_quantity__lte=models.F("target_quantity")),name="recall_quantity_bounds"),models.CheckConstraint(condition=models.Q(approval_status__in=['DRAFT', 'PENDING', 'APPROVED', 'REJECTED']),name="recall_approval_status_valid"),models.CheckConstraint(condition=models.Q(progress_status__in=['PLANNED', 'ACTIVE', 'COMPLETED', 'CLOSED']),name="recall_progress_status_valid")]

class RecallTarget(TimeStamped):
    recall=models.ForeignKey(Recall,on_delete=models.PROTECT,related_name="targets"); lot=models.ForeignKey(ProductLot,on_delete=models.PROTECT); serial_number=models.CharField(max_length=100,blank=True); target_quantity=models.PositiveIntegerField()
    class Meta:
        constraints=[models.UniqueConstraint(fields=["recall","lot","serial_number"],name="unique_recall_target"),models.CheckConstraint(condition=models.Q(target_quantity__gte=1),name="positive_recall_target")]

class RegulatoryReport(TimeStamped):
    class Status(models.TextChoices): DRAFT="DRAFT","작성"; REVIEW="REVIEW","검토"; APPROVED="APPROVED","승인"; SUBMITTED="SUBMITTED","제출"; REJECTED="REJECTED","반려"
    complaint=models.ForeignKey(CustomerComplaint,on_delete=models.PROTECT,related_name="reports"); document_number=models.CharField(max_length=50,unique=True); required=models.BooleanField(default=False); checklist=models.JSONField(default=dict,blank=True); investigation_result=models.TextField(blank=True); status=models.CharField(max_length=12,choices=Status.choices,default=Status.DRAFT); author=models.ForeignKey(User,on_delete=models.PROTECT,related_name="authored_reports"); reviewer=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name="reviewed_reports"); approved_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name="approved_reports"); approved_at=models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(status__in=['DRAFT', 'REVIEW', 'APPROVED', 'SUBMITTED', 'REJECTED']),name="regulatoryreport_status_valid")]

def upload_to(instance,filename): return f"attachments/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"

class Attachment(TimeStamped):
    ra_profile=models.ForeignKey("pms.RegulatoryProfile",on_delete=models.PROTECT,null=True,blank=True,related_name="ra_evidence")
    complaint=models.ForeignKey(CustomerComplaint,on_delete=models.PROTECT,null=True,blank=True,related_name="attachments"); file=models.FileField(upload_to=upload_to,validators=[FileExtensionValidator(["pdf","png","jpg","jpeg","txt","csv"])]); original_name=models.CharField(max_length=255,blank=True); uploaded_by=models.ForeignKey(User,on_delete=models.PROTECT)
    scan_status=models.CharField(max_length=12,choices=[("PENDING","검사 대기"),("PASSED","통과"),("QUARANTINED","격리"),("FAILED","검사 실패")],default="PENDING",db_index=True)
    sha256=models.CharField(max_length=64,blank=True)
    detected_type=models.CharField(max_length=20,blank=True)
    scanned_at=models.DateTimeField(null=True,blank=True)
    def clean(self):
        if self.file and self.file.size>settings.DATA_UPLOAD_MAX_MEMORY_SIZE: raise ValidationError("첨부파일 크기 제한을 초과했습니다.")
        if self.file:
            from .file_security import validate_upload
            validate_upload(self.file)
    class Meta:
        constraints=[models.CheckConstraint(condition=(models.Q(complaint__isnull=False,ra_profile__isnull=True)|models.Q(complaint__isnull=True,ra_profile__isnull=False)),name="attachment_one_context")]

class Approval(TimeStamped):
    superseded=models.BooleanField(default=False)
    class Meta:
        indexes=[models.Index(fields=["content_type","object_id","-created_at","-id"],name="approval_object_sequence")]
        constraints=[models.CheckConstraint(condition=models.Q(decision__in=['PENDING', 'APPROVED', 'REJECTED']),name="approval_decision_valid"),models.UniqueConstraint(fields=["content_type","object_id"],condition=models.Q(decision="PENDING",superseded=False,content_type="CustomerComplaint"),name="unique_pending_case_approval")]
    class Decision(models.TextChoices): PENDING="PENDING","대기"; APPROVED="APPROVED","승인"; REJECTED="REJECTED","반려"
    content_type=models.CharField(max_length=50); object_id=models.PositiveIntegerField(); requested_by=models.ForeignKey(User,on_delete=models.PROTECT,related_name="requested_approvals"); decided_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name="decided_approvals"); decision=models.CharField(max_length=10,choices=Decision.choices,default=Decision.PENDING); reason=models.TextField(blank=True); snapshot=models.JSONField(default=dict,blank=True); decided_at=models.DateTimeField(null=True,blank=True)
class AuditLog(AppendOnlyRecord):
    actor=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True); action=models.CharField(max_length=30); object_type=models.CharField(max_length=80,blank=True); object_id=models.CharField(max_length=80,blank=True); before=models.JSONField(default=dict,blank=True); after=models.JSONField(default=dict,blank=True); ip_address=models.GenericIPAddressField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-created_at"]
class Notification(TimeStamped):
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name="notifications"); title=models.CharField(max_length=200); message=models.TextField(); level=models.CharField(max_length=10,default="INFO"); due_at=models.DateTimeField(null=True,blank=True); read_at=models.DateTimeField(null=True,blank=True)
    dedupe_key=models.CharField(max_length=200,unique=True,null=True,blank=True)
class AssistantConversation(TimeStamped):
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name="assistant_conversations"); title=models.CharField(max_length=120,default="RA 업무 상담"); is_active=models.BooleanField(default=True)
    class Meta: ordering=["-updated_at"]
class AssistantMessage(models.Model):
    class Role(models.TextChoices): USER="USER","사용자"; ASSISTANT="ASSISTANT","RA 도우미"
    conversation=models.ForeignKey(AssistantConversation,on_delete=models.CASCADE,related_name="messages"); role=models.CharField(max_length=10,choices=Role.choices); content=models.TextField(max_length=4000); intent=models.CharField(max_length=40,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["created_at"]

class WorkTask(TimeStamped):
    class Status(models.TextChoices):
        WAITING="WAITING","대기"
        IN_PROGRESS="IN_PROGRESS","진행 중"
        REVIEW="REVIEW","검토 중"
        DONE="DONE","완료"
    market_comparison=models.OneToOneField("pms.MarketComparisonResult",on_delete=models.PROTECT,null=True,blank=True,related_name="review_task")
    ra_profile=models.ForeignKey("pms.RegulatoryProfile",on_delete=models.PROTECT,null=True,blank=True,related_name="work_tasks")
    complaint=models.ForeignKey(CustomerComplaint,on_delete=models.PROTECT,null=True,blank=True,related_name="tasks",verbose_name="사건")
    capa=models.ForeignKey(CAPA,on_delete=models.PROTECT,null=True,blank=True,related_name="tasks",verbose_name="CAPA")
    recall=models.ForeignKey(Recall,on_delete=models.PROTECT,null=True,blank=True,related_name="tasks",verbose_name="리콜")
    assignee=models.ForeignKey(User,on_delete=models.PROTECT,related_name="work_tasks",verbose_name="담당자")
    title=models.CharField("제목",max_length=200)
    description=models.TextField("설명",blank=True)
    priority=models.CharField("우선순위",max_length=10,choices=[("LOW","낮음"),("NORMAL","보통"),("HIGH","높음"),("URGENT","긴급")],default="NORMAL")
    due_at=models.DateTimeField("마감일")
    status=models.CharField("상태",max_length=16,choices=Status.choices,default=Status.WAITING)
    class Meta:
        constraints=[models.CheckConstraint(condition=(models.Q(complaint__isnull=False,ra_profile__isnull=True)|models.Q(complaint__isnull=True,ra_profile__isnull=False)),name="worktask_one_context"),models.CheckConstraint(condition=models.Q(capa__isnull=True)|models.Q(recall__isnull=True),name="task_one_action_parent"),models.CheckConstraint(condition=models.Q(status__in=['WAITING', 'IN_PROGRESS', 'REVIEW', 'DONE']),name="worktask_status_valid")]
        indexes=[models.Index(fields=["assignee","status","due_at"])]
        ordering=["due_at","pk"]
    def clean(self):
        super().clean()
        if self.market_comparison_id and self.complaint_id != self.market_comparison.entry.complaint_id:
            raise ValidationError("비교 검토 업무는 비교 결과의 사건에 연결해야 합니다.")
        if self.capa_id and self.capa.complaint_id != self.complaint_id: raise ValidationError("CAPA 사건이 일치하지 않습니다.")
        if self.recall_id and self.recall.complaint_id != self.complaint_id: raise ValidationError("리콜 사건이 일치하지 않습니다.")
        if self.capa_id and self.recall_id: raise ValidationError("CAPA 또는 리콜 중 하나만 연결하세요.")
    def __str__(self): return self.title

class TaskHistory(AppendOnlyRecord):
    task=models.ForeignKey(WorkTask,on_delete=models.PROTECT,related_name="history")
    actor=models.ForeignKey(User,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    before=models.JSONField(default=dict)
    after=models.JSONField(default=dict)

class CAPAEvaluation(models.Model):
    fixed_release = models.ForeignKey(SoftwareRelease, verbose_name="검증한 수정 릴리스", on_delete=models.PROTECT, null=True, blank=True)

    capa=models.ForeignKey(CAPA,on_delete=models.PROTECT,related_name="evaluations")
    action_result=models.TextField("조치 결과")
    criteria=models.TextField("평가 기준")
    scheduled_on=models.DateField("평가 예정일")
    evaluator=models.ForeignKey(User,on_delete=models.PROTECT,verbose_name="평가자")
    evaluated_on=models.DateField("평가일")
    verdict=models.CharField("판정",max_length=10,choices=[("PASS","적합"),("FAIL","미흡")])
    rationale=models.TextField("판정 근거")
    evidence=models.ManyToManyField(Attachment,blank=True,related_name="capa_evaluations",verbose_name="증빙")
    followup=models.OneToOneField(WorkTask,on_delete=models.PROTECT,null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-created_at","-pk"]
    def save(self,*args,**kwargs):
        with transaction.atomic():
            case = CustomerComplaint.objects.select_for_update().get(pk=self.capa.complaint_id)
            if self.fixed_release_id and self.fixed_release.device_id != case.device_id:
                raise ValidationError("수정 릴리스는 사건 제품에 속해야 합니다.")
            if self.pk:
                old=type(self).objects.get(pk=self.pk)
                if any(getattr(old,f.attname)!=getattr(self,f.attname) for f in self._meta.concrete_fields if f.name not in ('followup',)):
                    raise ValidationError('효과성 평가 내용은 수정할 수 없습니다. 재평가를 추가하세요.')
                if old.followup_id and old.followup_id!=self.followup_id: raise ValidationError('후속 업무는 교체할 수 없습니다.')
            if self.followup_id and (self.followup.complaint_id!=self.capa.complaint_id or self.followup.capa_id!=self.capa_id):
                raise ValidationError('효과성 평가와 후속 업무의 CAPA·사건이 일치하지 않습니다.')
            return super().save(*args,**kwargs)

class BusinessPartner(TimeStamped):
    name=models.CharField("거래처명",max_length=200,unique=True)
    def __str__(self): return self.name

class RecallRecipient(TimeStamped):
    recall=models.ForeignKey(Recall,on_delete=models.PROTECT,related_name="recipients",verbose_name="리콜")
    lot=models.ForeignKey(ProductLot,on_delete=models.PROTECT,verbose_name="로트")
    partner=models.ForeignKey(BusinessPartner,on_delete=models.PROTECT,verbose_name="거래처")
    unit=models.CharField("수량 단위",max_length=20,default="개")
    target_quantity=models.PositiveIntegerField("회수 대상 수량",validators=[MinValueValidator(1)])
    # Reservation counter maintained atomically with the immutable recovery ledger.
    recovered_total=models.PositiveIntegerField(default=0,editable=False)
    notified_on=models.DateField("통보일",null=True,blank=True)
    notification_method=models.CharField("통보 방법",max_length=100,blank=True)
    replied_on=models.DateField("회신일",null=True,blank=True)
    reply_status=models.CharField("회신 상태",max_length=12,choices=[("WAITING","대기"),("REPLIED","회신"),("DECLINED","회수 불가")],default="WAITING")
    unrecovered_reason=models.TextField("미회수 사유",blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["recall","lot","partner","unit"],name="unique_recall_recipient"),models.CheckConstraint(condition=models.Q(recovered_total__lte=models.F("target_quantity")),name="recipient_recovery_limit"),models.CheckConstraint(condition=models.Q(target_quantity__gte=1),name="positive_recipient_target")]
    @property
    def recovered_quantity(self): return self.recoveries.aggregate(total=models.Sum("quantity"))["total"] or 0
    @property
    def remaining_quantity(self): return self.target_quantity-self.recovered_quantity
    def clean(self):
        if self.lot_id and self.recall_id and self.lot.device_id != self.recall.device_id: raise ValidationError("리콜 제품과 LOT가 일치하지 않습니다.")
        if not self.unit.strip(): raise ValidationError("수량 단위는 필수입니다.")
    def __str__(self): return f"{self.partner} / {self.lot} ({self.unit})"

class RecoveryEntry(models.Model):
    def save(self,*args,**kwargs):
        if self.pk or not getattr(self,'_ledger_write',False):
            raise ValidationError('회수 원장은 record_recovery 서비스로만 추가할 수 있습니다.')
        return super().save(*args,**kwargs)
    def delete(self,*args,**kwargs): raise ValidationError('회수 원장은 삭제할 수 없습니다.')

    request_key=models.CharField(max_length=64,null=True,blank=True)
    recipient=models.ForeignKey(RecallRecipient,on_delete=models.PROTECT,related_name="recoveries")
    recovered_on=models.DateField("회수 일자")
    quantity=models.PositiveIntegerField("회수 수량",validators=[MinValueValidator(1)])
    actor=models.ForeignKey(User,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["recipient","request_key"],name="unique_recovery_request"),models.CheckConstraint(condition=models.Q(quantity__gte=1),name="positive_recovery_quantity")]

class RecallContact(AppendOnlyRecord):
    recipient=models.ForeignKey(RecallRecipient,on_delete=models.PROTECT,related_name="contacts")
    contacted_at=models.DateTimeField("연락 일시")
    method=models.CharField("연락 방법",max_length=100)
    note=models.TextField("후속 연락 내용")
    actor=models.ForeignKey(User,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)

class ReportingRule(TimeStamped):
    name=models.CharField("규칙명",max_length=200)
    version=models.PositiveIntegerField("버전",default=1,validators=[MinValueValidator(1)])
    conditions=models.JSONField("적용 조건",default=dict,blank=True,help_text='허용 키: complaint_type, risk_level, serious. 예: {"risk_level":"HIGH"}')
    basis=models.CharField("기준 시점",max_length=20,choices=[("REPORTED","접수 일시"),("OCCURRED","발생 일시"),("AWARE","인지 일시 (담당자 확인)"),("CUSTOM","별도 명시 기준 일시")],default="",blank=True)
    days=models.PositiveIntegerField("기한 값",null=True,blank=True,validators=[MaxValueValidator(3660)])
    day_type=models.CharField("기한 기준",max_length=12,choices=[("CALENDAR","달력일"),("BUSINESS","영업일")],default="",blank=True)
    holidays=models.JSONField("휴일 달력",default=list,blank=True,help_text='영업일은 토·일 제외 + 명시한 YYYY-MM-DD 목록. 공휴일 자동 제공 없음.')
    effective_on=models.DateField("시행일",null=True,blank=True)
    change_reason=models.TextField("변경 사유")
    is_example=models.BooleanField("예시·운영 적용 전 검토 필요",default=True)
    class State(models.TextChoices):
        LEGACY="LEGACY","기존 규칙·재검토 필요"
        DRAFT="DRAFT","초안"
        REVIEW="REVIEW","검토 요청"
        APPROVED="APPROVED","승인"
        EFFECTIVE="EFFECTIVE","시행"
        RETIRED="RETIRED","폐기"
    family_key=models.UUIDField(default=uuid.uuid4,editable=False,db_index=True)
    supersedes=models.ForeignKey("self",on_delete=models.PROTECT,null=True,blank=True,related_name="revisions")
    state=models.CharField("상태",max_length=12,choices=State.choices,default=State.DRAFT,db_index=True)
    created_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name="rule_drafts")
    reviewed_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name="rule_reviews")
    approved_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name="rule_approvals")
    approved_at=models.DateTimeField(null=True,blank=True)
    activated_at=models.DateTimeField(null=True,blank=True)
    revision=models.PositiveIntegerField(default=1,editable=False)
    jurisdiction=models.CharField("관할 국가·지역",max_length=120,blank=True)
    device=models.ForeignKey(MedicalDevice,on_delete=models.PROTECT,null=True,blank=True,verbose_name="대상 제품 (비우면 공통)")
    scope_description=models.TextField("적용 대상·범위",blank=True)
    reporting_authority=models.CharField("보고 대상 기관",max_length=200,blank=True)
    obligation_trigger=models.TextField("보고 의무 발생의 기준 사건",blank=True)
    deadline_expression=models.TextField("기한 원문 표현",blank=True)
    deadline_unit=models.CharField("기한 단위",max_length=8,choices=[("DAYS","일"),("HOURS","시간")],blank=True)
    include_start=models.BooleanField("시작일 포함",null=True,blank=True)
    deadline_time=models.TimeField("마감 시각",null=True,blank=True)
    timezone_name=models.CharField("시간대",max_length=64,blank=True)
    exceptions=models.TextField("예외 조건 (없으면 검토한 뒤 없음 명시)",blank=True)
    effective_until=models.DateField("시행 종료일",null=True,blank=True)
    holiday_verified_from=models.DateField("휴일 확인 시작일",null=True,blank=True)
    holiday_verified_until=models.DateField("휴일 확인 종료일",null=True,blank=True)
    holiday_checked_on=models.DateField("휴일 마지막 확인일",null=True,blank=True)
    unresolved_items=models.JSONField("확인 필요·충돌 사항",default=list,blank=True)
    source_expressions=models.JSONField("항목별 원문 표현",default=dict,blank=True)
    origin=models.CharField(max_length=12,choices=[("MANUAL","직접 작성"),("EVIDENCE","검색 근거로 작성"),("AI","AI 제안")],default="MANUAL")
    class Meta:
        constraints=[models.UniqueConstraint(fields=["name","version"],name="unique_reporting_rule_version"),models.UniqueConstraint(fields=["family_key","version"],name="unique_rule_family_version")]
    def clean(self):
        from .regulatory import validate_rule_content
        validate_rule_content(self)
    def save(self,*a,**kw):
        allowed=getattr(self,"_workflow_write",False)
        if self.pk:
            old=type(self).objects.get(pk=self.pk)
            if not allowed and (old.state!=self.State.DRAFT or self.state!=old.state):
                raise ValidationError("승인·검토 중·기존 버전은 직접 수정할 수 없습니다. 개정 초안을 만드세요.")
            if not allowed: raise ValidationError("변경 이력 보존을 위해 규칙 편집 화면을 사용하세요.")
        elif self.state!=self.State.DRAFT and not allowed:
            raise ValidationError("규칙은 초안으로만 생성할 수 있습니다.")
        self.full_clean()
        try: return super().save(*a,**kw)
        finally: self._workflow_write=False
    def __str__(self): return f"{self.name} v{self.version} · {self.get_state_display()}" + (" (예시·운영 적용 전 검토 필요)" if self.is_example else "")

class RuleApplication(AppendOnlyRecord):
    previous_snapshot=models.JSONField(default=dict,blank=True)
    complaint=models.ForeignKey(CustomerComplaint,on_delete=models.PROTECT,related_name="rule_applications")
    rule=models.ForeignKey(ReportingRule,on_delete=models.PROTECT)
    snapshot=models.JSONField()
    due_at=models.DateTimeField()
    actor=models.ForeignKey(User,on_delete=models.PROTECT)
    reason=models.TextField()
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-created_at","-pk"]

class ReportArtifact(AppendOnlyRecord):
    complaint=models.ForeignKey(CustomerComplaint,on_delete=models.PROTECT,related_name="artifacts")
    number=models.CharField(max_length=80)
    version=models.PositiveIntegerField()
    snapshot=models.JSONField()
    file=models.FileField(upload_to="private_reports/")
    bundle=models.FileField(upload_to="private_reports/",blank=True)
    sha256=models.CharField(max_length=64)
    bundle_sha256=models.CharField(max_length=64,blank=True)
    generated_by=models.ForeignKey(User,on_delete=models.PROTECT)
    generated_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["-version"]
        constraints=[models.UniqueConstraint(fields=["complaint","version"],name="unique_report_artifact_version")]

class LoginBucket(models.Model):
    key=models.CharField(max_length=64,unique=True)
    count=models.PositiveIntegerField(default=0)
    expires_at=models.DateTimeField(db_index=True)


class RegulationDocument(TimeStamped):
    title=models.CharField("문서명",max_length=240)
    issuer=models.CharField("발행 기관",max_length=200)
    jurisdiction=models.CharField("관할 국가·지역",max_length=120,db_index=True)
    device=models.ForeignKey(MedicalDevice,on_delete=models.PROTECT,null=True,blank=True,verbose_name="대상 제품 (비우면 공통)")
    scope_description=models.TextField("대상 제품·적용 범위")
    document_number=models.CharField("문서 번호",max_length=160)
    edition=models.CharField("개정 번호·버전",max_length=120)
    published_on=models.DateField("공표일",null=True,blank=True)
    effective_on=models.DateField("시행일",null=True,blank=True)
    official_url=models.URLField("공식 원문 URL (주소 기록만, 자동 수집 안 함)",max_length=1000,blank=True)
    file=models.FileField("원본 PDF·UTF-8 텍스트",upload_to=upload_to,max_length=255)
    original_name=models.CharField(max_length=255,blank=True)
    uploaded_by=models.ForeignKey(User,on_delete=models.PROTECT,verbose_name="등록자")
    visibility=models.CharField("접근 범위",max_length=12,choices=[("TEAM","RA 공동·승인 규칙 근거 공개"),("PRIVATE","등록자·관리자 전용")],default="TEAM")
    is_example=models.BooleanField("테스트용 문서",default=False)
    scan_status=models.CharField(max_length=12,choices=Attachment._meta.get_field("scan_status").choices,default="PENDING",db_index=True)
    sha256=models.CharField("원본 파일 SHA-256",max_length=64,blank=True)
    detected_type=models.CharField(max_length=20,blank=True)
    scanned_at=models.DateTimeField(null=True,blank=True)
    extraction_status=models.CharField("추출 상태",max_length=16,choices=[("PENDING","추출 대기"),("READY","추출 완료"),("OCR_REQUIRED","OCR 필요"),("FAILED","추출 실패"),("BLOCKED","파일 검사 필요")],default="PENDING",db_index=True)
    extraction_note=models.CharField(max_length=300,blank=True)
    review_status=models.CharField("검토 상태",max_length=12,choices=[("UNREVIEWED","미검토"),("REVIEWED","검토 완료"),("REJECTED","반려")],default="UNREVIEWED")
    reviewed_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True,related_name="reviewed_regulations")
    reviewed_at=models.DateTimeField(null=True,blank=True)
    review_reason=models.TextField(blank=True)
    class Meta:
        ordering=["-created_at"]
        indexes=[models.Index(fields=["jurisdiction","document_number","edition"])]
    def clean(self):
        if self.official_url and not self.official_url.startswith("https://"): raise ValidationError("공식 원문 URL은 HTTPS 주소만 기록합니다.")
        if self.file:
            from .file_security import validate_upload
            if Path(self.file.name).suffix.lower() not in (".pdf",".txt"): raise ValidationError("규정 문서는 PDF 또는 UTF-8 TXT만 지원합니다.")
            validate_upload(self.file)
    def save(self,*args,**kwargs):
        if self.pk:
            old=type(self).objects.get(pk=self.pk)
            protected=("title","issuer","jurisdiction","device_id","scope_description","document_number","edition","published_on","effective_on","official_url","file","original_name","uploaded_by_id","visibility","is_example","sha256")
            if any(getattr(old,key)!=getattr(self,key) for key in protected):
                raise ValidationError("문서 원본·출처·접근 범위는 변경할 수 없습니다. 새 문서 버전을 등록하세요.")
        return super().save(*args,**kwargs)
    def __str__(self): return f"{self.title} · {self.edition}"

class RegulationChunk(models.Model):
    document=models.ForeignKey(RegulationDocument,on_delete=models.PROTECT,related_name="chunks")
    sequence=models.PositiveIntegerField()
    page=models.PositiveIntegerField(null=True,blank=True)
    section=models.CharField(max_length=240,blank=True)
    paragraph=models.PositiveIntegerField()
    text=models.TextField()
    content_hash=models.CharField(max_length=64)
    search_tokens=models.JSONField(default=list)
    class Meta:
        ordering=["document_id","sequence"]
        constraints=[models.UniqueConstraint(fields=["document","sequence"],name="unique_document_chunk")]

class RuleCitation(models.Model):
    @property
    def field_label(self):
        from .regulatory import FIELD_LABELS
        return FIELD_LABELS.get(self.field_name,self.field_name)

    rule=models.ForeignKey(ReportingRule,on_delete=models.PROTECT,related_name="citations")
    field_name=models.CharField("근거 연결 항목",max_length=80)
    chunk=models.ForeignKey(RegulationChunk,on_delete=models.PROTECT,related_name="citations")
    quote=models.TextField("정확한 인용 문장")
    interpretation=models.TextField("RA 해석·검토 근거",blank=True)
    created_by=models.ForeignKey(User,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)

class RulePreview(AppendOnlyRecord):
    rule=models.ForeignKey(ReportingRule,on_delete=models.PROTECT,related_name="previews")
    fingerprint=models.CharField(max_length=64)
    inputs=models.JSONField()
    result=models.JSONField()
    created_by=models.ForeignKey(User,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)

class RuleChange(AppendOnlyRecord):
    @property
    def action_label(self):
        labels={"RULE_DRAFT_SAVE":"초안 저장","RULE_REVISE":"개정 초안 생성","RULE_CITATION_ADD":"근거 인용 추가","RULE_CITATION_REMOVE":"근거 인용 제거","RULE_HOLIDAY_IMPORT":"휴일 목록 가져오기","RULE_SUBMIT":"검토 요청","RULE_REJECT":"반려","RULE_APPROVE":"승인","RULE_ACTIVATE":"시행 승인","RULE_RETIRE":"폐기"}
        return labels.get(self.action,self.action)

    rule=models.ForeignKey(ReportingRule,on_delete=models.PROTECT,related_name="changes")
    actor=models.ForeignKey(User,on_delete=models.PROTECT)
    action=models.CharField(max_length=30)
    reason=models.TextField()
    before=models.JSONField(default=dict,blank=True)
    after=models.JSONField(default=dict,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-created_at","-pk"]

class RuleFamilyLock(models.Model):
    # One lock per existing rule family, shared across all writers/approvers.
    key=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)

from .analysis_models import AnalysisImport, AnalysisRecord, AnalysisReview, AnalysisReviewHistory
from .safety_models import SafetySignal, SafetyReview

class RegulatoryImpact(TimeStamped):
    old_rule=models.ForeignKey(ReportingRule,on_delete=models.PROTECT,related_name="old_impacts")
    new_rule=models.ForeignKey(ReportingRule,on_delete=models.PROTECT,related_name="new_impacts")
    created_by=models.ForeignKey(User,on_delete=models.PROTECT)
    snapshot=models.JSONField()
    include_closed=models.BooleanField(default=False)


class ImpactReview(TimeStamped):
    analysis=models.ForeignKey(RegulatoryImpact,on_delete=models.PROTECT,related_name="reviews")
    complaint=models.ForeignKey(CustomerComplaint,on_delete=models.PROTECT,related_name="impact_reviews")
    task=models.OneToOneField(WorkTask,on_delete=models.PROTECT)
    status=models.CharField(max_length=16,choices=[("WAITING","검토 대기"),("IN_PROGRESS","검토 중"),("APPLIED","적용 완료"),("EXCLUDED","적용 제외")],default="WAITING")
    snapshot=models.JSONField()
    shortened=models.BooleanField(default=False)
    reason=models.TextField(blank=True)
    processed_by=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True)
    processed_at=models.DateTimeField(null=True,blank=True)
    application=models.OneToOneField(RuleApplication,on_delete=models.PROTECT,null=True,blank=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(status__in=['WAITING', 'IN_PROGRESS', 'APPLIED', 'EXCLUDED']),name="impactreview_status_valid"),models.UniqueConstraint(fields=["analysis","complaint"],name="unique_impact_case")]


# Collector deletions and evidence membership changes also participate in the case lock.
from django.db.models.signals import pre_delete, m2m_changed
from django.dispatch import receiver

@receiver(pre_delete)
def lock_approval_input_delete(sender,instance,using,**kwargs):
    if sender not in (RiskAssessment,AdverseEvent,CAPA,RegulatoryReport,Recall,Attachment,RecallTarget,RecallRecipient,CAPAEvaluation): return
    case_id=getattr(instance,'complaint_id',None)
    if sender in (RecallTarget,RecallRecipient): case_id=instance.recall.complaint_id
    if sender==CAPAEvaluation: case_id=instance.capa.complaint_id
    if case_id: CustomerComplaint.objects.using(using).select_for_update().get(pk=case_id)

@receiver(m2m_changed,sender=CAPAEvaluation.evidence.through)
def lock_evaluation_evidence(sender,instance,action,reverse,using,pk_set=None,**kwargs):
    if not action.startswith('pre_'): return
    if action == 'pre_add':
        if reverse:
            invalid=CAPAEvaluation.objects.filter(pk__in=pk_set).exclude(capa__complaint_id=instance.complaint_id).exists() or instance.scan_status!='PASSED'
        else:
            invalid=Attachment.objects.filter(pk__in=pk_set).exclude(complaint_id=instance.capa.complaint_id,scan_status='PASSED').exists()
        if invalid: raise ValidationError('동일 사건의 검사 통과 증빙만 연결할 수 있습니다.')
    ids=[instance.complaint_id] if reverse else [instance.capa.complaint_id]
    for case_id in ids: CustomerComplaint.objects.using(using).select_for_update().get(pk=case_id)


class ImmutableHistory(models.Model):
    actor=models.ForeignKey(User,on_delete=models.PROTECT,null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    reason=models.TextField(blank=True)
    source=models.CharField(max_length=20,choices=[('APPLICATION','Application'),('DIRECT_MODEL','Direct model; actor unknown')])
    before=models.JSONField(default=dict)
    after=models.JSONField(default=dict)
    class Meta: abstract=True
    def save(self,*args,**kwargs):
        if self.pk: raise ValidationError('이력은 수정할 수 없습니다.')
        return super().save(*args,**kwargs)
    def delete(self,*args,**kwargs): raise ValidationError('이력은 삭제할 수 없습니다.')

class RiskAssessmentHistory(ImmutableHistory):
    parent=models.ForeignKey(RiskAssessment,on_delete=models.PROTECT,related_name='history')
    class Meta:
        ordering=['created_at','pk']
        indexes=[models.Index(fields=['parent','created_at'],name='risk_history_parent_time')]

class RegulatoryReportHistory(ImmutableHistory):
    parent=models.ForeignKey(RegulatoryReport,on_delete=models.PROTECT,related_name='history')
    class Meta:
        ordering=['created_at','pk']
        indexes=[models.Index(fields=['parent','created_at'],name='report_history_parent_time')]


@receiver(pre_delete)
def preserve_history_rows(sender,instance,**kwargs):
    if sender in (RiskAssessmentHistory,RegulatoryReportHistory,RecoveryEntry,CAPAEvaluation,TaskHistory,AnalysisReviewHistory,SafetyReview,RuleChange,RuleApplication,ReportArtifact,AuditLog,RecallContact,RulePreview):
        raise ValidationError('평가·보고 이력은 삭제할 수 없습니다.')


from .ra_models import RegulatoryProfile, RARequirement, MarketingAuthorization, AuthorizationEvent, SubmissionPackage

from .ra_models import ProductRevision, ControlledDocument, ProductChange, LabelVersion

from .ra_models import RiskCriteria, ProductRisk, SafetyInformation, FieldSafetyAction, FieldActionRecipient, FieldActionContact, FieldActionEvaluation, SupplierRecord, SupplierMaterial

from .ra_models import TrainingRequirement, TrainingAssignment, AuditPlan, AuditFinding, AuditPackage, ManagementReview, ManagementDecision, RetentionPolicy
from . import ra_operations_models
from . import foreign_models
from . import market_models
