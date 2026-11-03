from hashlib import sha256
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from .test_ra_platform import RAReviewFixture
from . import ra_models as ra, ra_services as s, ra_operations as ops
from . import ra_operations_models as o
from .models import Attachment, AuditLog


class RAOperationsTests(RAReviewFixture):
    def evidence(self, content, name='fixture.txt'):
        return Attachment.objects.create(
            ra_profile=self.profile, file=SimpleUploadedFile(name,content),
            original_name=name, uploaded_by=self.raqa, scan_status='PASSED',
            sha256=sha256(content).hexdigest(),
        )

    def effective_document(self, number):
        obj=self.approve(self.document(number))
        return s.transition(obj,self.admin,'activate','시험용 시행',obj.revision)

    def quality_form(self):
        parent=None
        for level in ('MANUAL','PROCEDURE','INSTRUCTION','FORM'):
            parent=self.approve(self.create(
                o.QualityDocument,document=self.effective_document(level),parent=parent,
                department='합성 품질팀',level=level,
                required_fields=['lot'] if level=='FORM' else [],
                template_approved=level=='FORM',
            ))
        return parent

    def project(self):
        release=self.create(ra.ProductRevision,version='EEG-DEMO-2',description='가상 뇌파 분석 제품')
        return self.create(o.DHFProject,release=release,purpose='합성 시나리오')

    def test_form_approval_correction_retirement_and_template(self):
        form=self.quality_form()
        record=self.create(o.QualityRecord,form_version=form,record_key='FORM-01')
        self.assertEqual(ops.dashboard_context(record)['missing_fields'],['lot'])
        record=s.save_record(record,self.raqa,{'values':{'lot':'DEMO-A'}},'작성',record.revision)
        original=self.approve(record)
        cloned=ops.template_draft(form,self.raqa,'FORM-DRAFT-02','템플릿 초안')
        self.assertEqual(cloned.state,'DRAFT')
        self.assertEqual(o.QualityDocument.objects.get(document=cloned).template_source_id,form.document_id)
        s.transition(form.document,self.admin,'retire','대체 예정',form.document.revision)
        with self.assertRaises(ValidationError):
            self.create(o.QualityRecord,form_version=form,record_key='FORM-02')
        correction=self.approve(self.create(o.QualityRecord,form_version=form,record_key='FORM-01-C1',corrects=original,values={'lot':'DEMO-B'}))
        self.assertEqual(correction.corrects.values,{'lot':'DEMO-A'})
        self.assertEqual(original.approval_snapshot['content']['values'],{'lot':'DEMO-A'})
        with self.assertRaises(ValidationError):
            self.create(o.QualityRecord,form_version=form,record_key='FORM-01-C1',corrects=original)

    def test_validation_preserves_execution_and_requires_approved_waiver(self):
        plan=self.create(o.QualityValidation,system_version='QMS-DEMO-1',intended_use='기록 추적',quality_impact='누락 위험',plan='시험 계획',acceptance='계획 기준',report='내부 결과',internal_confirmation='담당자 확인')
        req=self.approve(self.create(o.ValidationRequirement,validation=plan,requirement='버전 유지',risk='기록 손실',control='이력 확인'))
        case=self.approve(self.create(o.ValidationCase,requirement=req,procedure='기록 열기',expected='원본 유지'))
        with self.assertRaises(ValidationError):
            ops.approval_gate(plan)
        with self.assertRaises(ValidationError):
            self.create(o.ValidationRun,case=case,outcome='WAIVED',result='시험 제외')
        file=self.evidence(b'synthetic execution')
        fail=self.create(o.ValidationRun,case=case,outcome='FAIL',result='미충족',deviation='누락')
        fail=s.save_record(fail,self.raqa,{},'증빙',fail.revision,{'evidence':[file]})
        fail=self.approve(fail)
        with self.assertRaises(ValidationError):
            ops.approval_gate(plan)
        waiver=self.create(o.ValidationRun,case=case,outcome='WAIVED',result='별도 시험에서 범위 확인',deviation='담당자 면제 검토',retest_of=fail)
        with self.assertRaises(ValidationError):
            ops.approval_gate(plan)
        self.approve(waiver)
        final=self.approve(plan)
        self.assertEqual(final.approval_snapshot['content']['requirement_trace'][0]['cases'][0]['runs'][0]['outcome'],'FAIL')
        self.assertEqual(fail.case_id,case.pk)

    def test_meeting_provenance_and_dhf_snapshot(self):
        project=self.project()
        doc=self.effective_document('EEG-SPEC')
        file=self.evidence('설계 출력 EEG-SPEC v1 담당: 검토팀, 2026-11-10 https://example.invalid'.encode())
        meeting=self.create(o.MeetingSource,project=project,minutes=file,meeting_on=timezone.localdate())
        self.assertEqual(ops.extract(meeting,self.raqa),1)
        self.assertEqual(ops.extract(meeting,self.raqa),0)
        candidate=o.MeetingCandidate.objects.get(meeting=meeting)
        self.assertEqual(candidate.document,doc)
        self.assertEqual(candidate.line_number,1)
        with self.assertRaises(ValidationError):
            ops.confirm(candidate,self.raqa,'검토 전')
        with self.assertRaises(ValidationError):
            s.schedule_task(candidate,self.raqa,timezone.localdate())
        candidate=self.approve(candidate)
        trace=ops.confirm(candidate,self.raqa,'원문 확인')
        self.assertEqual(ops.confirm(candidate,self.raqa,'재요청').pk,trace.pk)
        baseline=self.create(o.DHFBaseline,project=project)
        ops.capture(baseline,self.raqa,'기준 캡처')
        baseline.refresh_from_db()
        self.assertEqual(baseline.baseline['release_version'],'EEG-DEMO-2')
        self.assertEqual(baseline.baseline['rows'][0]['links']['output']['id'],doc.pk)
        self.client.force_login(self.staff)
        url=f'/ra/dhf-baselines/{baseline.pk}/dhf-export/'
        self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.raqa)
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertIn(f'/ra/documents/{doc.pk}/'.encode(),response.content)
        from django.conf import settings
        if settings.PDF_KOREAN_FONT:
            self.assertTrue(self.client.get(url+'?format=pdf').content.startswith(b'%PDF'))

    def test_sbom_import_needs_scoped_evidence_and_security_review(self):
        project=self.project()
        sbom=self.evidence(b'name,version,source\nsynthetic-lib,1.0,local-test\n','sbom.csv')
        inv=self.create(o.SecurityInventory,release=project.release,sbom=sbom)
        ops.import_sbom(inv,self.raqa,'시험용 SBOM')
        inv.refresh_from_db()
        self.assertEqual(inv.components[0]['version'],'1.0')
        self.assertEqual(inv.state,'DRAFT')
        review=self.create(o.SecurityReview,inventory=inv,test_plan='경계 입력 시험')
        with self.assertRaises(ValidationError):
            ops.approval_gate(review)
        with self.assertRaises(PermissionDenied):
            ops.import_sbom(inv,self.staff,'권한 확인')

    def test_change_review_requires_ready_document_and_exact_package(self):
        project=self.project()
        before=self.create(ra.ProductRevision,version='EEG-DEMO-1',description='이전 합성 버전')
        change=self.create(ra.ProductChange,category='SOFTWARE',from_revision=before,to_revision=project.release,before_content='고정 필터',after_content='선택 필터',reason='가상 기능 변경')
        authorization=self.create(ra.MarketingAuthorization,kind='가상 인허가')
        package=self.approve(self.create(ra.SubmissionPackage,authorization=authorization,version=1,content_description='합성 기술문서 목록',change=change,product_revision=project.release))
        review=self.create(o.SoftwareChangeReview,change=change,project=project,classification='담당자 내부 검토 분류',classification_basis='가상 변경 영향',function_comparison='필터 설정',algorithm_comparison='선택 필터',intended_use_comparison='가상 목적 비교',package=package)
        with self.assertRaises(ValidationError):
            ops.approval_gate(review)
        doc=self.effective_document('EEG-TECH-01')
        self.create(o.TechnicalSection,review=review,section='알고리즘 비교',readiness='READY',document=doc)
        review=self.approve(review)
        self.assertEqual(review.submission_manifest['package_hash'],package.approval_snapshot['hash'])
        self.assertEqual(review.submission_manifest['sections'][0]['document'],doc.pk)
