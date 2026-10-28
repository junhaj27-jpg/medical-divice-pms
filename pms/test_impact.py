from django.test import override_settings
from django.core.exceptions import ValidationError, PermissionDenied
from django.urls import reverse
from . import test_regulatory as fixtures
from .tests import Base
from .models import Notification, WorkTask, ImpactReview, ReportingRule
from .impact import create_analysis, process_review, stale_reason, notify_review, analyses_for
from .regulatory import revise_rule, save_draft, transition_rule


# Reuse fixture helpers without inheriting the existing test methods.
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ImpactTests(Base):
    def setUp(self):
        import uuid, shutil
        from pathlib import Path
        super().setUp()
        self.root=Path('.test-media')/uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree,self.root)
        media=override_settings(MEDIA_ROOT=self.root/'media');media.enable();self.addCleanup(media.disable)
        self.c=self.complaint();self.c.is_example=True;self.c.complaint_type='TEST_EVENT';self.c.save()
    document=fixtures.RegulatoryTests.document
    draft=fixtures.RegulatoryTests.draft
    cite_all=fixtures.RegulatoryTests.cite_all
    publish=fixtures.RegulatoryTests.publish
    apply=fixtures.RegulatoryTests.apply
    def pair(self):
        old=self.draft();new=revise_rule(old,self.raqa,'TEST-only revision')
        new.days=1;new=save_draft(new,self.raqa,'TEST shorter',expected_revision=new.revision)
        return old,new
    def inputs(self):
        return {str(self.c.pk):{'jurisdiction':'TEST-REGION','basis_at':f'{self.c.reported_on}T10:00:00+09:00'}}
    def test_new_scope_and_no_case_mutation(self):
        old,new=self.pair();before=(self.c.due_date,self.c.version,self.c.rule_applications.count())
        analysis=create_analysis(old,new,self.raqa,inputs=self.inputs());review=analysis.reviews.get()
        self.assertTrue(any('NEW_SCOPE' in x for x in review.snapshot['reasons']))
        self.assertFalse(review.snapshot['result']['error']);self.c.refresh_from_db()
        self.assertEqual(before,(self.c.due_date,self.c.version,self.c.rule_applications.count()))
        self.assertRaises(ValidationError,process_review,review,self.raqa,'APPLIED','explicit test')
    def test_old_application_distinguished_and_shortening(self):
        old=self.publish(self.cite_all(self.draft()));self.apply(old)
        new=revise_rule(old,self.raqa,'TEST revision');new.days=1;new=save_draft(new,self.raqa,'TEST shorter',expected_revision=new.revision)
        analysis=create_analysis(old,new,self.raqa,inputs=self.inputs());review=analysis.reviews.get()
        self.assertEqual(len(review.snapshot['reasons']),2);self.assertTrue(review.shortened)
        self.c.complaint_type='different';self.c.save()
        other=create_analysis(old,new,self.raqa).reviews.get()
        self.assertEqual(len(other.snapshot['reasons']),1);self.assertIn('OLD_APPLICATION',other.snapshot['reasons'][0])
    def test_closed_cases_excluded_by_default(self):
        old=self.publish(self.cite_all(self.draft()));self.apply(old);new=revise_rule(old,self.raqa,'TEST revision')
        self.c.status='CLOSED';self.c.save()
        self.assertFalse(create_analysis(old,new,self.raqa).reviews.exists())
        self.assertEqual(create_analysis(old,new,self.raqa,include_closed=True).reviews.count(),1)
    def test_missing_jurisdiction_and_basis_not_inferred(self):
        old,new=self.pair();review=create_analysis(old,new,self.raqa).reviews.get()
        self.assertIn('관할',review.snapshot['result']['error'])
        inputs={str(self.c.pk):{'jurisdiction':'TEST-REGION'}}
        review=create_analysis(old,new,self.raqa,inputs=inputs).reviews.get()
        self.assertIn('기준 일시',review.snapshot['result']['error'])
    def test_period_and_holiday_errors(self):
        old,new=self.pair();new.effective_on=self.c.reported_on.replace(year=self.c.reported_on.year+1)
        new=save_draft(new,self.raqa,'TEST period',expected_revision=new.revision)
        self.assertIn('시행일',create_analysis(old,new,self.raqa,inputs=self.inputs()).reviews.get().snapshot['result']['error'])
        new.effective_on=old.effective_on;new.day_type='BUSINESS'
        new=save_draft(new,self.raqa,'TEST holiday',expected_revision=new.revision)
        self.assertIn('휴일 확인',create_analysis(old,new,self.raqa,inputs=self.inputs()).reviews.get().snapshot['result']['error'])
    def test_case_and_rule_staleness(self):
        old,new=self.pair();r=create_analysis(old,new,self.raqa).reviews.get()
        self.c.title='changed';self.c.save();self.assertIn('사건',stale_reason(r,self.raqa))
        r=create_analysis(old,new,self.raqa).reviews.get();new.days=8;save_draft(new,self.raqa,'TEST update',expected_revision=new.revision)
        r.refresh_from_db();self.assertIn('규칙',stale_reason(r,self.raqa))
    def test_review_reason_dedupe_and_completed_history(self):
        old,new=self.pair();r=create_analysis(old,new,self.raqa).reviews.get();before=r.snapshot.copy()
        notify_review(r);notify_review(r);self.assertEqual(Notification.objects.filter(dedupe_key__startswith=f'impact:{r.pk}:').count(),1)
        self.assertEqual(WorkTask.objects.filter(pk=r.task_id).count(),1)
        self.assertRaises(ValidationError,process_review,r,self.raqa,'EXCLUDED','')
        process_review(r,self.raqa,'IN_PROGRESS','reviewing');process_review(r,self.raqa,'EXCLUDED','outside jurisdiction')
        r.refresh_from_db();self.assertEqual(r.snapshot,before);self.assertEqual(r.task.status,'DONE')
        self.assertRaises(ValidationError,process_review,r,self.raqa,'WAITING')
    def test_staff_and_private_draft_access(self):
        old,new=self.pair();a=create_analysis(old,new,self.raqa)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('impact-list')).status_code,403)
        self.assertEqual(self.client.get(reverse('impact-detail',args=[a.pk])).status_code,403)
        self.assertFalse(analyses_for(self.staff).exists());self.assertRaises(PermissionDenied,create_analysis,old,new,self.staff)
        self.client.force_login(self.raqa)
        self.assertContains(self.client.get(reverse('impact-detail',args=[a.pk])),'NEW_SCOPE')
        self.assertEqual(self.client.get(reverse('impact-detail',args=[a.pk])+'?shortened=1').status_code,200)
        from django.contrib.auth.models import User
        from .models import Profile
        other=User.objects.create_user('TEST-other-RA');Profile.objects.create(user=other,role='RA_QA')
        self.assertFalse(analyses_for(other).filter(pk=a.pk).exists())
        self.assertRaises(PermissionDenied,create_analysis,old,new,other)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('impact-detail',args=[a.pk])).status_code,404)
    def test_explicit_application_reuses_real_service(self):
        old=self.publish(self.cite_all(self.draft()));self.apply(old)
        new=revise_rule(old,self.raqa,'TEST revision');new.days=1;new=save_draft(new,self.raqa,'TEST shorter',expected_revision=new.revision)
        transition_rule(old,self.admin,'retire','TEST replacement');new=self.publish(new)
        r=create_analysis(old,new,self.raqa,inputs=self.inputs()).reviews.get()
        process_review(r,self.raqa,'APPLIED','explicit TEST reapplication')
        r.refresh_from_db();self.assertEqual(r.status,'APPLIED');self.assertEqual(r.application.rule_id,new.pk)
        self.assertEqual(self.c.rule_applications.count(),2)
