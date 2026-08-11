import uuid
from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

class TimeStamped(models.Model):
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: abstract=True

class Profile(models.Model):
    class Role(models.TextChoices): STAFF="STAFF","직원"; RA_QA="RA_QA","RA/QA"; ADMIN="ADMIN","관리자"
    user=models.OneToOneField(User,on_delete=models.CASCADE,related_name="profile"); role=models.CharField(max_length=10,choices=Role.choices,default=Role.STAFF)
    def __str__(self): return f"{self.user.username} ({self.role})"

class Manufacturer(TimeStamped):
    name=models.CharField(max_length=200,unique=True); country=models.CharField(max_length=100,blank=True); contact_email=models.EmailField(blank=True)
    def __str__(self): return self.name
class MedicalDevice(TimeStamped):
    manufacturer=models.ForeignKey(Manufacturer,on_delete=models.PROTECT,related_name="devices"); name=models.CharField(max_length=200); model_number=models.CharField(max_length=100); risk_class=models.CharField(max_length=20,blank=True); active=models.BooleanField(default=True)
    class Meta: unique_together=("manufacturer","model_number")
    def __str__(self): return f"{self.name} ({self.model_number})"
class UDI(TimeStamped):
    device=models.ForeignKey(MedicalDevice,on_delete=models.CASCADE,related_name="udis"); device_identifier=models.CharField(max_length=100,unique=True)
    def __str__(self): return self.device_identifier
class ProductLot(TimeStamped):
    device=models.ForeignKey(MedicalDevice,on_delete=models.CASCADE,related_name="lots"); udi=models.ForeignKey(UDI,on_delete=models.PROTECT,related_name="lots"); lot_number=models.CharField(max_length=100); serial_number=models.CharField(max_length=100,blank=True); manufactured_on=models.DateField(null=True,blank=True); expires_on=models.DateField(null=True,blank=True); distributed_quantity=models.PositiveIntegerField(default=0)
    class Meta: unique_together=("udi","lot_number","serial_number")
    def __str__(self): return f"{self.lot_number} / {self.serial_number or '-'}"

class CustomerComplaint(TimeStamped):
    class Status(models.TextChoices): RECEIVED="RECEIVED","접수"; REVIEW="REVIEW","RA/QA 검토"; AE_DECISION="AE_DECISION","이상사례 판단"; RISK="RISK","위험평가"; CAPA_DECISION="CAPA_DECISION","CAPA 판단"; REPORT_REVIEW="REPORT_REVIEW","규제보고 검토"; RECALL_REVIEW="RECALL_REVIEW","리콜 검토"; APPROVAL="APPROVAL","관리자 승인"; ACTION_COMPLETE="ACTION_COMPLETE","조치 완료"; CLOSED="CLOSED","종료"
    device=models.ForeignKey(MedicalDevice,on_delete=models.PROTECT,related_name="complaints"); udi=models.ForeignKey(UDI,on_delete=models.PROTECT); lot=models.ForeignKey(ProductLot,on_delete=models.PROTECT,null=True,blank=True,related_name="complaints"); serial_number=models.CharField(max_length=100,blank=True); complaint_type=models.CharField(max_length=50,db_index=True); title=models.CharField(max_length=200); description=models.TextField(); occurred_on=models.DateField(); reported_on=models.DateField(default=timezone.localdate); reporter=models.ForeignKey(User,on_delete=models.PROTECT,related_name="reported_complaints"); assignee=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="assigned_complaints"); status=models.CharField(max_length=20,choices=Status.choices,default=Status.RECEIVED); due_date=models.DateField(null=True,blank=True); version=models.PositiveIntegerField(default=1)
    class Meta: ordering=["-created_at"]
    def __str__(self): return f"CMP-{self.pk or 'NEW'} {self.title}"
class PatientAnonymousInfo(TimeStamped):
    complaint=models.OneToOneField(CustomerComplaint,on_delete=models.CASCADE,related_name="patient_info"); anonymous_code=models.CharField(max_length=64,unique=True); age_band=models.CharField(max_length=20,blank=True); sex=models.CharField(max_length=20,blank=True); notes=models.TextField(blank=True)
    def clean(self):
        forbidden=("name","phone","resident","이름","전화","주민")
        if any(x in self.notes.lower() for x in forbidden): raise ValidationError("직접 식별정보는 저장할 수 없습니다.")
class AdverseEvent(TimeStamped):
    complaint=models.OneToOneField(CustomerComplaint,on_delete=models.CASCADE,related_name="adverse_event"); patient=models.ForeignKey(PatientAnonymousInfo,on_delete=models.PROTECT,null=True,blank=True); event_type=models.CharField(max_length=50); outcome=models.CharField(max_length=100); serious=models.BooleanField(default=False); narrative=models.TextField()
class RiskAssessment(TimeStamped):
    complaint=models.OneToOneField(CustomerComplaint,on_delete=models.CASCADE,related_name="risk_assessment"); severity=models.PositiveSmallIntegerField(validators=[MinValueValidator(1),MaxValueValidator(5)]); probability=models.PositiveSmallIntegerField(validators=[MinValueValidator(1),MaxValueValidator(5)]); score=models.PositiveSmallIntegerField(default=1,editable=False); level=models.CharField(max_length=10,editable=False); capa_review_required=models.BooleanField(default=False,editable=False); rationale=models.TextField(blank=True); assessed_by=models.ForeignKey(User,on_delete=models.PROTECT)
    def save(self,*a,**kw):
        self.score=self.severity*self.probability
        self.level="LOW" if self.score<=4 else "MEDIUM" if self.score<=9 else "HIGH" if self.score<=16 else "CRITICAL"
        self.capa_review_required=self.score>=10; super().save(*a,**kw)
class CAPA(TimeStamped):
    class Status(models.TextChoices): OPEN="OPEN","개시"; INVESTIGATION="INVESTIGATION","조사"; IMPLEMENTATION="IMPLEMENTATION","실행"; EFFECTIVENESS="EFFECTIVENESS","효과확인"; CLOSED="CLOSED","종료"
    complaint=models.ForeignKey(CustomerComplaint,on_delete=models.CASCADE,related_name="capas"); title=models.CharField(max_length=200); root_cause=models.TextField(blank=True); corrective_action=models.TextField(); preventive_action=models.TextField(blank=True); owner=models.ForeignKey(User,on_delete=models.PROTECT); due_date=models.DateField(); status=models.CharField(max_length=20,choices=Status.choices,default=Status.OPEN)
class Recall(TimeStamped):
    class Approval(models.TextChoices): DRAFT="DRAFT","작성"; PENDING="PENDING","승인대기"; APPROVED="APPROVED","승인"; REJECTED="REJECTED","반려"
    class Progress(models.TextChoices): PLANNED="PLANNED","계획"; ACTIVE="ACTIVE","진행"; COMPLETED="COMPLETED","완료"; CLOSED="CLOSED","종료"
    complaint=models.ForeignKey(CustomerComplaint,on_delete=models.SET_NULL,null=True,blank=True,related_name="recalls"); title=models.CharField(max_length=200); reason=models.TextField(); risk_level=models.CharField(max_length=10); device=models.ForeignKey(MedicalDevice,on_delete=models.PROTECT,related_name="recalls"); distributed_quantity=models.PositiveIntegerField(); target_quantity=models.PositiveIntegerField(); recovered_quantity=models.PositiveIntegerField(default=0); start_date=models.DateField(); expected_end_date=models.DateField(); owner=models.ForeignKey(User,on_delete=models.PROTECT); approval_status=models.CharField(max_length=10,choices=Approval.choices,default=Approval.DRAFT); progress_status=models.CharField(max_length=10,choices=Progress.choices,default=Progress.PLANNED); closure_report=models.TextField(blank=True)
    def clean(self):
        if self.target_quantity>self.distributed_quantity: raise ValidationError("회수 목표 수량은 유통 수량을 초과할 수 없습니다.")
        if self.recovered_quantity>self.target_quantity: raise ValidationError("실제 회수 수량은 목표 수량을 초과할 수 없습니다.")
    @property
    def recovery_rate(self): return round(self.recovered_quantity/self.target_quantity*100,1) if self.target_quantity else 0
class RecallTarget(TimeStamped):
    recall=models.ForeignKey(Recall,on_delete=models.CASCADE,related_name="targets"); lot=models.ForeignKey(ProductLot,on_delete=models.PROTECT); serial_number=models.CharField(max_length=100,blank=True); target_quantity=models.PositiveIntegerField()
class RegulatoryReport(TimeStamped):
    class Status(models.TextChoices): DRAFT="DRAFT","작성"; REVIEW="REVIEW","검토"; APPROVED="APPROVED","승인"; SUBMITTED="SUBMITTED","제출"; REJECTED="REJECTED","반려"
    complaint=models.ForeignKey(CustomerComplaint,on_delete=models.PROTECT,related_name="reports"); document_number=models.CharField(max_length=50,unique=True); required=models.BooleanField(default=False); checklist=models.JSONField(default=dict,blank=True); investigation_result=models.TextField(blank=True); status=models.CharField(max_length=12,choices=Status.choices,default=Status.DRAFT); author=models.ForeignKey(User,on_delete=models.PROTECT,related_name="authored_reports"); reviewer=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="reviewed_reports"); approved_by=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="approved_reports"); approved_at=models.DateTimeField(null=True,blank=True)
def upload_to(instance,filename): return f"attachments/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
class Attachment(TimeStamped):
    complaint=models.ForeignKey(CustomerComplaint,on_delete=models.CASCADE,related_name="attachments"); file=models.FileField(upload_to=upload_to,validators=[FileExtensionValidator(["pdf","png","jpg","jpeg","txt","csv"])]); original_name=models.CharField(max_length=255,blank=True); uploaded_by=models.ForeignKey(User,on_delete=models.PROTECT)
    def clean(self):
        if self.file and self.file.size>settings.DATA_UPLOAD_MAX_MEMORY_SIZE: raise ValidationError("첨부파일 크기 제한을 초과했습니다.")
class Approval(TimeStamped):
    class Decision(models.TextChoices): PENDING="PENDING","대기"; APPROVED="APPROVED","승인"; REJECTED="REJECTED","반려"
    content_type=models.CharField(max_length=50); object_id=models.PositiveIntegerField(); requested_by=models.ForeignKey(User,on_delete=models.PROTECT,related_name="requested_approvals"); decided_by=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="decided_approvals"); decision=models.CharField(max_length=10,choices=Decision.choices,default=Decision.PENDING); reason=models.TextField(blank=True); snapshot=models.JSONField(default=dict,blank=True); decided_at=models.DateTimeField(null=True,blank=True)
class AuditLog(models.Model):
    actor=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True); action=models.CharField(max_length=30); object_type=models.CharField(max_length=80,blank=True); object_id=models.CharField(max_length=80,blank=True); before=models.JSONField(default=dict,blank=True); after=models.JSONField(default=dict,blank=True); ip_address=models.GenericIPAddressField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-created_at"]
class Notification(TimeStamped):
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name="notifications"); title=models.CharField(max_length=200); message=models.TextField(); level=models.CharField(max_length=10,default="INFO"); due_at=models.DateTimeField(null=True,blank=True); read_at=models.DateTimeField(null=True,blank=True)
