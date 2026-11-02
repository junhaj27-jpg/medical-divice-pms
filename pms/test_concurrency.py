"""Real row-lock checks: each worker owns an independent PostgreSQL connection."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest import skipUnless
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection, connections, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from .models import Manufacturer, MedicalDevice, UDI, CustomerComplaint, Approval, RiskAssessment
from .services import request_complaint_approval, decide_approval, transition_complaint


@skipUnless(connection.vendor=='postgresql','Requires actual PostgreSQL; SQLite cannot verify row locks')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ApprovalConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.admin=User.objects.create_superuser('TEST-concurrency-admin')
        maker=Manufacturer.objects.create(name='TEST concurrency')
        device=MedicalDevice.objects.create(manufacturer=maker,name='TEST',model_number='TEST')
        udi=UDI.objects.create(device=device,device_identifier='TEST-CONCURRENCY')
        self.case=CustomerComplaint.objects.create(device=device,udi=udi,reporter=self.admin,title='TEST only',description='synthetic',complaint_type='TEST',occurred_on=timezone.localdate(),status='APPROVAL',is_example=True)

    def race(self, action):
        barrier=Barrier(2)
        def run(index):
            try:
                connections['default'].ensure_connection()
                with connections['default'].cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()');pid=cursor.fetchone()[0]
                barrier.wait(timeout=10)
                try: action(index);return ('ok',pid)
                except ValidationError: return ('blocked',pid)
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,range(2)))
        self.assertNotEqual(results[0][1],results[1][1])
        self.assertEqual(sorted(x[0] for x in results),['blocked','ok'])

    def test_duplicate_request_is_serialized(self):
        self.race(lambda _:request_complaint_approval(self.case,self.admin))
        self.assertEqual(Approval.objects.filter(decision='PENDING',superseded=False).count(),1)

    def test_first_approval_or_rejection_wins(self):
        approval=request_complaint_approval(self.case,self.admin)
        self.race(lambda i:decide_approval(approval,self.admin,'APPROVED' if i==0 else 'REJECTED','TEST reason'))
        approval.refresh_from_db();self.assertIn(approval.decision,('APPROVED','REJECTED'))

    def test_transition_only_once(self):
        approval=request_complaint_approval(self.case,self.admin);decide_approval(approval,self.admin,'APPROVED')
        self.race(lambda _:transition_complaint(self.case,'ACTION_COMPLETE',self.admin))
        self.case.refresh_from_db();self.assertEqual(self.case.version,2)

    def test_related_writer_cannot_cross_approval_lock(self):
        risk=RiskAssessment.objects.create(complaint=self.case,severity=2,probability=2,assessed_by=self.admin)
        approval=request_complaint_approval(self.case,self.admin)
        started=Event();finished=Event()
        def writer():
            try:
                started.set();obj=RiskAssessment.objects.get(pk=risk.pk)
                obj.rationale='TEST changed';obj.save();finished.set()
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                CustomerComplaint.objects.select_for_update().get(pk=self.case.pk)
                future=pool.submit(writer);self.assertTrue(started.wait(5))
                self.assertFalse(finished.wait(.2))
                decide_approval(approval,self.admin,'APPROVED')
            future.result(timeout=10)
        self.assertRaises(ValidationError,transition_complaint,self.case,'ACTION_COMPLETE',self.admin)

    def test_internal_snapshot_concurrent_duplicate(self):
        from .internal_cohort import internal_payload, import_internal
        from .analysis import digest
        from .analysis_models import AnalysisRecord
        expected={str(self.case.pk):digest(internal_payload(self.case))}
        barrier=Barrier(2)
        def run(_):
            try:
                connections['default'].ensure_connection()
                with connections['default'].cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()');pid=cursor.fetchone()[0]
                barrier.wait(timeout=10)
                return pid,import_internal(self.admin,expected)
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,range(2)))
        self.assertNotEqual(results[0][0],results[1][0])
        self.assertEqual(sorted(len(r[1]) for r in results),[0,1])
        self.assertEqual(AnalysisRecord.objects.filter(source_case=self.case).count(),1)

    def test_same_case_concurrent_rule_reapplication(self):
        import tempfile, shutil
        from pathlib import Path
        from . import test_regulatory as fixtures
        from .models import Profile
        from .regulatory import revise_rule, save_draft, transition_rule, preview_rule, apply_regulated_rule
        from .impact import case_token, rule_token
        self.raqa=User.objects.create_user('TEST-concurrent-ra')
        Profile.objects.create(user=self.raqa,role='RA_QA')
        self.c=self.case;self.c.complaint_type='TEST_EVENT';self.c.save()
        root=Path('.test-media');root.mkdir(exist_ok=True)
        import uuid
        self.root=root/uuid.uuid4().hex;self.root.mkdir();self.addCleanup(shutil.rmtree,self.root)
        media=override_settings(MEDIA_ROOT=self.root/'media');media.enable();self.addCleanup(media.disable)
        self.document=lambda *a,**k:fixtures.RegulatoryTests.document(self,*a,**k)
        self.draft=lambda *a,**k:fixtures.RegulatoryTests.draft(self,*a,**k)
        self.cite_all=lambda *a,**k:fixtures.RegulatoryTests.cite_all(self,*a,**k)
        self.publish=lambda *a,**k:fixtures.RegulatoryTests.publish(self,*a,**k)
        old=self.publish(self.cite_all(self.draft()))
        first=fixtures.RegulatoryTests.apply(self,old)
        new=revise_rule(old,self.raqa,'TEST revision');new.days=1
        new=save_draft(new,self.raqa,'TEST shorter',expected_revision=new.revision)
        transition_rule(old,self.admin,'retire','TEST replacement');new=self.publish(new)
        self.c.refresh_from_db()
        preview=preview_rule(new,self.raqa,f'{self.c.reported_on}T10:00:00+09:00')
        due=str(self.c.due_date or '');token=case_token(self.c);rtoken=rule_token(new)
        self.race(lambda _:apply_regulated_rule(self.c,new,self.raqa,preview,'TEST explicit reapply',first.pk,due,token,rtoken))
        self.assertEqual(self.c.rule_applications.filter(rule=new).count(),1)
