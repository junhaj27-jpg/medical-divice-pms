import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import connections, close_old_connections
from django.core.exceptions import ValidationError
from django.test import TransactionTestCase, override_settings
from .tests import Base
from .models import CAPA, SafetySignal, SignalTracking
from .safety import scope_for
from .signal_tracking import track_signal


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TrackingConcurrencyTests(TransactionTestCase):
    def test_simultaneous_action_requests_then_retry_have_one_draft(self):
        Base.setUp(self)
        case=Base.complaint(self)
        signal=SafetySignal.objects.create(key='concurrent',scope=scope_for(self.raqa),assignee=self.raqa,
            snapshot={'group':{'device_id':self.d.pk},'evidence':[{'pk':case.pk}]})
        barrier=Barrier(2)
        data=dict(request_key=str(uuid.uuid4()),kind='DRAFT_CAPA',complaint=case.pk,confirm=True,due_on='2026-12-01',note='명시적 요청')
        def send():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return track_signal(self.raqa,signal.pk,data).pk
            except ValidationError:
                return None  # A SQLite lock conflict is recoverable with the same key.
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:send(),range(2)))
        record=track_signal(self.raqa,signal.pk,data)
        self.assertEqual(CAPA.objects.count(),1)
        self.assertEqual(SignalTracking.objects.filter(kind='DRAFT_CAPA').count(),1)
        self.assertTrue(all(r is None or r==record.pk for r in results))
