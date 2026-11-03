from datetime import timedelta
from django.test import override_settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from .tests import Base
from .models import BusinessPartner, WorkTask, Notification, AuditLog
from . import ra_models as m
from . import ra_services as s
from .workflow import notify_tasks

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RAScopeFixture(Base):
    def setUp(self):
        super().setUp()
        self.partner=BusinessPartner.objects.create(name='TEST RA organization')
        self.profile=s.save_record(m.RegulatoryProfile(),self.raqa,dict(title='TEST profile',device=self.d,jurisdiction='미확인 관할',organization=self.partner,organization_role='MANUFACTURER',owner=self.raqa,reviewer=self.admin),'범위 초안')
    def create(self,cls,**values):
        data=dict(profile=self.profile,title='TEST '+cls.__name__,owner=self.raqa,reviewer=self.admin);data.update(values)
        return s.save_record(cls(),self.raqa,data,'실제 기준 미확인 테스트')


class RAScopeTests(RAScopeFixture):
    def test_unverified_and_source_requirements(self):
        self.assertEqual(self.profile.applicability,'UNVERIFIED')
        self.assertRaises(ValidationError,s.save_record,self.profile,self.raqa,{'applicability':'APPLIES','rationale':'test'},'검토',self.profile.revision)
        self.profile.refresh_from_db();self.assertEqual(self.profile.applicability,'UNVERIFIED')
    def test_requirement_and_conflicting_revision(self):
        obj=self.create(m.RARequirement,internal_id='INT-1',activity='담당자 기준 검토')
        changed=s.save_record(obj,self.raqa,{'activity':'문서 검토'},'추가 검토',obj.revision)
        self.assertRaises(ValidationError,s.save_record,obj,self.raqa,{'activity':'덮어쓰기'},'stale',1)
        self.assertEqual(changed.activity,'문서 검토')
    def test_authorization_events_no_invented_expiry(self):
        obj=self.create(m.MarketingAuthorization,kind='미확인 신청',status='APPLICATION')
        self.assertIsNone(obj.expires_on);self.assertEqual(obj.events.count(),1)
        obj=s.save_record(obj,self.raqa,{'status':'SUPPLEMENT'},'기관 보완 요청 수동 기록',obj.revision)
        self.assertEqual(list(obj.events.order_by('pk').values_list('status',flat=True)),['APPLICATION','SUPPLEMENT'])
        self.assertRaises(ValidationError,s.save_record,obj,self.raqa,{'status':'APPROVED','number':'123'},'번호만 입력',obj.revision)
    def test_reused_task_and_notification_dedupe(self):
        obj=self.create(m.MarketingAuthorization,kind='TEST')
        due=timezone.localdate()+timedelta(days=1)
        a=s.schedule_task(obj,self.raqa,due);b=s.schedule_task(obj,self.raqa,due)
        self.assertEqual(a.pk,b.pk);self.assertIsNone(a.complaint_id);self.assertEqual(a.ra_profile,self.profile)
        self.assertEqual(notify_tasks(),1);self.assertEqual(notify_tasks(),0)
    def test_task_context_db_constraint(self):
        with self.assertRaises(IntegrityError),transaction.atomic():
            WorkTask.objects.bulk_create([WorkTask(title='invalid',assignee=self.raqa,due_at=timezone.now())])
    def test_approval_snapshot_and_read_only_package(self):
        auth=self.create(m.MarketingAuthorization,kind='TEST')
        obj=self.create(m.SubmissionPackage,authorization=auth,version=1,content_description='초안 파일 목록')
        for action,actor in [('submit',self.raqa),('review',self.admin),('approve',self.admin)]: obj=s.transition(obj,actor,action,'검토 근거',obj.revision)
        self.assertTrue(obj.frozen_snapshot);before=obj.frozen_snapshot.copy()
        self.assertRaises(ValidationError,s.save_record,obj,self.raqa,{'content_description':'overwrite'},'test',obj.revision)
        obj.refresh_from_db();self.assertEqual(obj.frozen_snapshot,before)
    def test_urls_api_and_csrf_permissions(self):
        self.client.force_login(self.staff)
        for url in ['/ra/','/ra/profiles/','/ra/profiles/%s/'%self.profile.pk,'/ra/api/profiles/']:
            self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.raqa)
        self.assertContains(self.client.get('/ra/'),'제품 규제 프로필')
        self.assertEqual(self.client.get('/ra/api/profiles/%s/'%self.profile.pk).json()['content']['applicability'],'UNVERIFIED')
        self.assertEqual(self.client.delete('/ra/api/profiles/%s/'%self.profile.pk).status_code,405)

class RAReviewFixture(RAScopeFixture):
    def approve(self,obj):
        for action,actor in [('submit',self.raqa),('review',self.admin),('approve',self.admin)]: obj=s.transition(obj,actor,action,'실제 담당자 검토 테스트',obj.revision)
        return obj
    def document(self,number='SOP-TEST'):
        return self.create(m.ControlledDocument,category='SOP',number=number,version=1,body='초안 본문',change_reason='최초 등록',effective_on=timezone.localdate())


class RAChangeTests(RAReviewFixture):
    def test_document_freeze_revision_and_effective_version(self):
        obj=self.approve(self.document())
        self.assertRaises(ValidationError,s.save_record,obj,self.raqa,{'body':'changed'},'test',obj.revision)
        obj=s.transition(obj,self.admin,'activate','시행 확인',obj.revision)
        revised=s.revise_document(obj,self.raqa,'새 개정')
        self.assertEqual(revised.version,2);self.assertEqual(revised.supersedes,obj);self.assertEqual(obj.body,revised.body)
        self.assertTrue(s.compare_documents(revised))
    def test_change_cannot_implement_unapproved_or_unverified(self):
        first=self.create(m.ProductRevision,version='v1',description='이전 구성')
        second=self.create(m.ProductRevision,version='v2',description='새 구성')
        obj=self.create(m.ProductChange,category='SOFTWARE',from_revision=first,to_revision=second,before_content='v1',after_content='v2',reason='검증 변경')
        self.assertRaises(ValidationError,s.transition,obj,self.admin,'implement','시행 시도',obj.revision)
        obj=s.transition(obj,self.raqa,'submit','test',obj.revision);obj=s.transition(obj,self.admin,'review','test',obj.revision)
        self.assertRaises(ValidationError,s.transition,obj,self.admin,'approve','근거 미확인',obj.revision)
    def test_label_requires_translation_review(self):
        document=self.approve(self.document())
        document=s.transition(document,self.admin,'activate','시행',document.revision)
        product=self.create(m.ProductRevision,version='label-v1',description='표시 대상')
        label=self.create(m.LabelVersion,artifact_type='IFU',language='ko',version=1,document=document,product_revision=product,effective_on=timezone.localdate())
        label=s.transition(label,self.raqa,'submit','test',label.revision);label=s.transition(label,self.admin,'review','test',label.revision)
        self.assertRaises(ValidationError,s.transition,label,self.admin,'approve','자동 번역만 존재',label.revision)

class RARiskSafetyTests(RAReviewFixture):
    def test_product_risk_requires_product_specific_approved_criteria(self):
        criteria=self.create(m.RiskCriteria,version=1,estimation_method='제품별 정성 추정',acceptance_criteria='조직의 확인 기준',basis='시험 기준')
        risk=self.create(m.ProductRisk,criteria=criteria,hazard='에너지',hazardous_situation='노출',harm='손상',estimate='담당자가 정성 추정')
        risk=s.transition(risk,self.raqa,'submit','test',risk.revision);risk=s.transition(risk,self.admin,'review','test',risk.revision)
        self.assertRaises(ValidationError,s.transition,risk,self.admin,'approve','기준 미승인',risk.revision)
        self.assertFalse(hasattr(risk,'severity'));self.assertEqual(risk.residual_decision,'UNVERIFIED')
    def test_external_information_duplicate_and_reason(self):
        obj=self.create(m.SafetyInformation,source_url='https://example.test/official-not-verified',source_identifier='S-1')
        self.assertRaises(ValidationError,self.create,m.SafetyInformation,source_url=obj.source_url,source_identifier='S-1')
        self.assertRaises(ValidationError,s.save_record,obj,self.raqa,{'reporting_decision':'NOT_REQUIRED'},'근거 없음',obj.revision)
    def test_supplier_has_no_invented_renewal_cycle(self):
        supplier=self.create(m.SupplierRecord,partner=self.partner,supplier_type='CONTRACTOR',process_service='멸균 서비스',evaluation_criteria='조직별 검토, 자동 주기 없음')
        material=self.create(m.SupplierMaterial,supplier=supplier,category='QUALITY_AGREEMENT',version='A')
        self.assertIsNone(material.expires_on);self.assertIsNone(material.next_review_on)
    def test_recall_has_no_duplicate_ra_recovery_ledger(self):
        from .models import Recall
        recall=Recall.objects.create(device=self.d,title='TEST',reason='test',risk_level='LOW',distributed_quantity=10,target_quantity=5,start_date=timezone.localdate(),expected_end_date=timezone.localdate(),owner=self.raqa)
        doc=self.document()
        action=self.create(m.FieldSafetyAction,action_type='RECALL',recall=recall,notice_document=doc,rationale='test')
        self.assertRaises(ValidationError,self.create,m.FieldActionRecipient,action=action,partner=self.partner,lot=self.lot,target_quantity=5)

class RATrainingAuditTests(RAReviewFixture):
    def test_training_assignments_are_explicit_and_view_is_not_completion(self):
        doc=self.approve(self.document());doc=s.transition(doc,self.admin,'activate','시행',doc.revision)
        requirement=self.create(m.TrainingRequirement,document=doc,required_role='STAFF',effectiveness_method='담당자 실습 확인')
        requirement=self.approve(requirement)
        created=s.sync_training(requirement,self.raqa)
        self.assertEqual(len(created),2)
        self.assertEqual(s.sync_training(requirement,self.raqa),[])
        assignment=requirement.assignments.get(trainee=self.staff)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/my-training/%s/'%assignment.pk).status_code,200)
        assignment.refresh_from_db();self.assertEqual(assignment.training_status,'PENDING')
        foreign=requirement.assignments.get(trainee=self.other)
        self.assertEqual(self.client.get('/my-training/%s/'%foreign.pk).status_code,404)
        self.assertRaises(ValidationError,s.save_record,assignment,self.raqa,{'training_status':'COMPLETED'},'증빙 없음',assignment.revision)
        self.staff.is_active=False;self.staff.save();s.sync_training(requirement,self.raqa)
        assignment.refresh_from_db();self.assertEqual(assignment.training_status,'INACTIVE')
    def test_audit_finding_capa_is_existing_model(self):
        plan=self.create(m.AuditPlan,audit_type='INTERNAL',scheduled_on=timezone.localdate(),scope='TEST 범위',criteria='조직 기준')
        finding=self.create(m.AuditFinding,audit=plan,observation='관찰',classification='미비',classification_basis='내부 분류 기준')
        finding=self.approve(finding)
        self.assertRaises(ValidationError,s.transition,finding,self.admin,'close','효과 미확인',finding.revision)
        self.assertEqual(AuditLog.objects.filter(object_type='AuditFinding',object_id=str(finding.pk),action='RA_APPROVE').count(),1)
    def test_management_snapshot_is_current_not_historical_or_incidence(self):
        obj=self.create(m.ManagementReview,period_start=timezone.localdate()-timedelta(days=30),period_end=timezone.localdate())
        obj=s.capture_management_review(obj,self.raqa,'기준일 캡처',obj.revision)
        self.assertIn('현재 상태',obj.management_snapshot['state_basis'])
        self.assertIsNone(obj.management_snapshot['incidence_rate'])
        self.assertEqual(obj.management_snapshot['complaint_report_count'],0)
        old=obj.management_snapshot.copy();self.complaint()
        obj.refresh_from_db();self.assertEqual(old,obj.management_snapshot)
        approved=self.approve(obj);self.assertIn('management_snapshot',approved.approval_snapshot['content'])
    def test_retention_is_organization_policy_without_automatic_deletion(self):
        obj=s.save_record(m.RetentionPolicy(),self.raqa,dict(title='조직 정책 초안',owner=self.raqa,organization=self.partner,record_category='RA 증빙',retention_basis='근거 확인 필요'),'정책 검토')
        self.assertFalse(obj.automatic_deletion);self.assertIsNone(obj.duration_days)

class RAIntegrationTests(RAReviewFixture):
    def evidence(self):
        import hashlib
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import Attachment
        return Attachment.objects.create(ra_profile=self.profile,file=SimpleUploadedFile('TEST-evidence.txt',b'TEST synthetic evidence'),original_name='TEST-evidence.txt',uploaded_by=self.raqa,scan_status='PASSED',sha256=hashlib.sha256(b'TEST synthetic evidence').hexdigest())
    def test_all_ra_screens_and_form_errors(self):
        self.client.force_login(self.raqa)
        for kind in s.REGISTRY:
            self.assertEqual(self.client.get(f'/ra/{kind}/').status_code,200,kind)
            expected=405 if kind=='meeting-candidates' else 200
            self.assertEqual(self.client.get(f'/ra/{kind}/new/').status_code,expected,kind)
            self.assertEqual(self.client.post(f'/ra/{kind}/new/',{}).status_code,expected,kind)
    def test_json_api_create_rejects_system_fields_and_bad_shape(self):
        import json
        self.client.force_login(self.raqa)
        self.assertEqual(self.client.post('/ra/api/requirements/',data='[]',content_type='application/json').status_code,400)
        self.assertEqual(self.client.post('/ra/api/requirements/',data=json.dumps({'data':{'state':'APPROVED'}}),content_type='application/json').status_code,400)
        response=self.client.post('/ra/api/requirements/',data=json.dumps({'reason':'TEST','data':{'profile':self.profile.pk,'title':'API test','owner':self.raqa.pk,'internal_id':'API-REQ','activity':'TEST activity','applicability':'UNVERIFIED','fulfillment':'UNVERIFIED'}}),content_type='application/json')
        self.assertEqual(response.status_code,201,response.content)
    def test_database_choices_and_protected_deletion(self):
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ValidationError),transaction.atomic():
            m.RegulatoryProfile.objects.filter(pk=self.profile.pk).delete()
        self.assertRaises(ProtectedError,self.d.delete)
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.RegulatoryProfile.objects.filter(pk=self.profile.pk).update(applicability='invented')
    def test_cross_profile_evidence_and_direct_relation_mutation(self):
        obj=self.document();file=self.evidence()
        with self.assertRaises(ValidationError),transaction.atomic(): obj.evidence.add(file)
        obj=s.save_record(obj,self.raqa,{},'증빙 검토',obj.revision,{'evidence':[file]})
        self.assertEqual(obj.evidence.count(),1)
        other=s.save_record(m.RegulatoryProfile(),self.raqa,dict(title='other',device=self.d,jurisdiction='OTHER',organization=self.partner,organization_role='IMPORTER',owner=self.raqa),'scope')
        self.assertRaises(ValidationError,s.save_record,obj,self.raqa,{'profile':other},'프로필 이동',obj.revision)
        self.assertEqual(obj.evidence.count(),1)
    def test_package_zip_snapshot_and_file_tamper(self):
        import io,zipfile
        from .file_security import private_path
        file=self.evidence()
        auth=self.create(m.MarketingAuthorization,kind='TEST')
        package=self.create(m.SubmissionPackage,authorization=auth,version=1,content_description='검토 제출본')
        package=s.save_record(package,self.raqa,{},'파일 연결',package.revision,{'evidence':[file]})
        package=self.approve(package)
        original=package.frozen_snapshot.copy()
        content=s.package_bytes(package,self.raqa)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertIn('manifest.json',archive.namelist());self.assertEqual(len(archive.namelist()),2)
        private_path(file.file).write_bytes(b'tampered')
        from django.core.exceptions import PermissionDenied
        self.assertRaises(PermissionDenied,s.package_bytes,package,self.raqa)
        package.refresh_from_db();self.assertEqual(package.frozen_snapshot,original)
    def test_positive_field_action_workflow_and_no_extra_recovery(self):
        file=self.evidence();doc=self.approve(self.document());doc=s.transition(doc,self.admin,'activate','시행',doc.revision)
        action=self.create(m.FieldSafetyAction,action_type='NOTICE',notice_document=doc,rationale='TEST 안내',effectiveness_criteria='전 대상 확인',closure_rationale='TEST 결과 확인')
        recipient=self.create(m.FieldActionRecipient,action=action,partner=self.partner,lot=self.lot,target_quantity=2)
        action=self.approve(action);action=s.transition(action,self.admin,'activate','시행',action.revision)
        recipient=s.save_record(recipient,self.raqa,{'notified_on':timezone.localdate(),'acknowledged_on':timezone.localdate(),'completed_on':timezone.localdate(),'completed_quantity':2,'outcome':'담당자 확인 증빙'},'실제 조치 기록',recipient.revision)
        s.record_field_contact(recipient,self.raqa,'전화','TEST 실제 연락',file)
        s.evaluate_field_action(action,self.raqa,'EFFECTIVE','TEST 효과 확인',file)
        action=s.transition(action,self.admin,'close','종결 확인',action.revision)
        self.assertEqual(action.state,'CLOSED');self.assertEqual(recipient.contacts.count(),1)
    def test_due_planner_idempotence_and_no_missing_expiry_guess(self):
        obj=self.create(m.MarketingAuthorization,kind='TEST',renewal_prepare_on=timezone.localdate())
        missing=self.create(m.MarketingAuthorization,kind='NO_EXPIRY')
        first=s.plan_due_reviews(self.raqa);second=s.plan_due_reviews(self.raqa)
        self.assertEqual([task.pk for task in first],[task.pk for task in second])
        self.assertEqual(obj.tasks.count(),1);self.assertEqual(missing.tasks.count(),0)
    def test_authorization_reopens_without_rewriting_approval_event(self):
        obj=self.approve(self.create(m.MarketingAuthorization,kind='TEST',status='APPLICATION'))
        original=obj.approval_snapshot.copy()
        obj=s.transition(obj,self.raqa,'reopen','보완 수동 기록',obj.revision)
        obj=s.save_record(obj,self.raqa,{'status':'SUPPLEMENT'},'기관 보완 수신',obj.revision)
        self.assertEqual(obj.events.count(),2)
        self.assertEqual(obj.approval_snapshot,original)
        self.assertEqual(obj.state,'DRAFT')
    def test_change_records_actual_implementation_after_approval(self):
        a=self.create(m.ProductRevision,version='CHANGE-A',description='이전')
        b=self.create(m.ProductRevision,version='CHANGE-B',description='이후')
        obj=self.create(m.ProductChange,category='MATERIAL',from_revision=a,to_revision=b,before_content='전',after_content='후',reason='시험',impact_checklist={k:'담당자 내부 검토 근거' for k in ['authorization','risk','validation','label','training','pms']},submission_decision='NOT_REQUIRED',decision_basis='법적 기준 미확인 예시 검토')
        obj=self.approve(obj)
        self.assertIsNone(obj.implemented_on)
        obj=s.transition(obj,self.admin,'implement','시행 확인',obj.revision,{'confirmation':'TEST 시행을 담당자가 확인'})
        self.assertEqual(obj.implemented_on,timezone.localdate());self.assertEqual(obj.state,'EFFECTIVE')
    def test_profile_scope_cannot_be_reparented(self):
        self.assertRaises(ValidationError,s.save_record,self.profile,self.raqa,{'jurisdiction':'changed'},'허가 범위 이동',self.profile.revision)
    def test_csrf_enforced_for_ra_json(self):
        from django.test import Client
        import json
        client=Client(enforce_csrf_checks=True);client.force_login(self.raqa)
        response=client.post('/ra/api/profiles/',data=json.dumps({}),content_type='application/json')
        self.assertEqual(response.status_code,403)

    def test_retraining_preserves_previous_attempt(self):
        doc=self.approve(self.document());doc=s.transition(doc,self.admin,'activate','시행',doc.revision)
        requirement=self.approve(self.create(m.TrainingRequirement,document=doc,required_role='STAFF',effectiveness_method='TEST 담당자 확인'))
        initial=self.create(m.TrainingAssignment,requirement=requirement,trainee=self.staff,training_status='RETRAIN',effectiveness='FAIL',effectiveness_rationale='효과 미흡')
        repeat=self.create(m.TrainingAssignment,requirement=requirement,trainee=self.staff,attempt=2,retraining_of=initial)
        self.assertEqual(repeat.retraining_of,initial);initial.refresh_from_db();self.assertEqual(initial.effectiveness,'FAIL')
        self.assertRaises(ValidationError,self.create,m.TrainingAssignment,requirement=requirement,trainee=self.staff,attempt=3)

    def test_opt_in_training_gate_applies_to_ra_only(self):
        doc=self.approve(self.document());doc=s.transition(doc,self.admin,'activate','시행',doc.revision)
        requirement=self.approve(self.create(m.TrainingRequirement,document=doc,required_role='ADMIN',effectiveness_method='실습 확인',enforce_ra_approval=True))
        s.sync_training(requirement,self.raqa)
        product=self.create(m.ProductRevision,version='TRAINING-TEST',description='TEST')
        product=s.transition(product,self.raqa,'submit','test',product.revision);product=s.transition(product,self.admin,'review','test',product.revision)
        self.assertRaises(ValidationError,s.transition,product,self.admin,'approve','교육 미완료',product.revision)
        assignment=requirement.assignments.get(trainee=self.admin)
        file=self.evidence()
        s.save_record(assignment,self.raqa,dict(training_status='COMPLETED',completed_on=timezone.localdate(),completion_evidence=file,effectiveness='PASS',effectiveness_rationale='실습 직접 확인'),'수료 검토',assignment.revision)
        product=s.transition(product,self.admin,'approve','교육 근거 확인',product.revision)
        self.assertEqual(product.state,'APPROVED')
