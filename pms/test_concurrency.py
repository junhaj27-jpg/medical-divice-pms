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
