"""PostgreSQL-only RA lock checks; SQLite skips these rather than simulating success."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.test import TransactionTestCase,override_settings
from django.utils import timezone
from .models import BusinessPartner,Manufacturer,MedicalDevice,Profile,AuditLog
from . import ra_models as m
from . import ra_services as s

@skipUnless(connection.vendor=='postgresql','Requires actual PostgreSQL row locks')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RAConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.author=User.objects.create_user('ra-concurrent-author')
        Profile.objects.create(user=self.author,role='RA_QA')
        self.admin=User.objects.create_superuser('ra-concurrent-admin')
        maker=Manufacturer.objects.create(name='TEST maker')
        device=MedicalDevice.objects.create(manufacturer=maker,name='TEST',model_number='RA-CONCURRENT')
        partner=BusinessPartner.objects.create(name='TEST partner')
        self.profile=s.save_record(m.RegulatoryProfile(),self.author,dict(title='TEST',device=device,jurisdiction='TEST only',organization=partner,organization_role='MANUFACTURER',owner=self.author,reviewer=self.admin,is_example=True),'synthetic test')
    def run_race(self,action):
        barrier=Barrier(2)
        def worker(index):
            try:
                with connections['default'].cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()');pid=cursor.fetchone()[0]
                barrier.wait(timeout=10)
                try: action(index);return (pid,'ok')
                except ValidationError: return (pid,'blocked')
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(worker,range(2)))
        self.assertNotEqual(results[0][0],results[1][0])
        self.assertEqual(sorted(item[1] for item in results),['blocked','ok'])
    def reviewed(self,obj):
        obj=s.transition(obj,self.author,'submit','test',obj.revision)
        return s.transition(obj,self.admin,'review','test',obj.revision)
    def test_one_approval_for_same_revision(self):
        obj=self.reviewed(self.profile)
        self.run_race(lambda _:s.transition(obj,self.admin,'approve','test',obj.revision))
        self.assertEqual(AuditLog.objects.filter(action='RA_APPROVE',object_type='RegulatoryProfile',object_id=str(obj.pk)).count(),1)
    def test_competing_document_versions_have_one_effective(self):
        docs=[]
        for version in (1,2):
            doc=s.save_record(m.ControlledDocument(),self.author,dict(profile=self.profile,title='TEST',owner=self.author,reviewer=self.admin,category='SOP',number='SOP-CONCURRENT',version=version,body='TEST',change_reason='TEST',effective_on=timezone.localdate(),is_example=True),'test')
            doc=self.reviewed(doc);docs.append(s.transition(doc,self.admin,'approve','test',doc.revision))
        self.run_race(lambda i:s.transition(docs[i],self.admin,'activate','test',docs[i].revision))
        self.assertEqual(m.ControlledDocument.objects.filter(state='EFFECTIVE',profile=self.profile).count(),1)
