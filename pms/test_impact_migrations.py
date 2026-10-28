from datetime import date
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ApprovalLegacyMigrationTests(TransactionTestCase):
    def test_existing_records_snapshots_paths_and_status_are_preserved(self):
        previous=('pms','0007_regulationchunk_regulationdocument_rulechange_and_more')
        executor=MigrationExecutor(connection);executor.migrate([previous])
        try:
            apps=executor.loader.project_state([previous]).apps
            User=apps.get_model('auth','User');u=User.objects.create(username='TEST-migration')
            M=apps.get_model('pms','Manufacturer');D=apps.get_model('pms','MedicalDevice');U=apps.get_model('pms','UDI')
            maker=M.objects.create(name='TEST migration');device=D.objects.create(manufacturer=maker,name='TEST',model_number='TEST');udi=U.objects.create(device=device,device_identifier='TEST-MIGRATION')
            C=apps.get_model('pms','CustomerComplaint')
            case=C.objects.create(device=device,udi=udi,reporter=u,occurred_on=date(2026,1,1),title='TEST',description='TEST',complaint_type='TEST',status='ACTION_COMPLETE',due_date=date(2026,1,9))
            A=apps.get_model('pms','Approval');snapshot={'version':2,'legacy':'keep unchanged'}
            old=A.objects.create(content_type='CustomerComplaint',object_id=case.pk,requested_by=u,snapshot=snapshot)
            new=A.objects.create(content_type='CustomerComplaint',object_id=case.pk,requested_by=u,snapshot=snapshot)
            approved=A.objects.create(content_type='CustomerComplaint',object_id=case.pk,requested_by=u,snapshot=snapshot,decision='APPROVED')
            F=apps.get_model('pms','Attachment');f=F.objects.create(complaint=case,file='attachments/legacy/relative.txt',uploaded_by=u)
            executor=MigrationExecutor(connection);leaves=executor.loader.graph.leaf_nodes();executor.migrate(leaves)
            current=executor.loader.project_state(leaves).apps
            A=current.get_model('pms','Approval');C=current.get_model('pms','CustomerComplaint');F=current.get_model('pms','Attachment')
            self.assertEqual(A.objects.count(),3);self.assertTrue(A.objects.get(pk=old.pk).superseded);self.assertFalse(A.objects.get(pk=new.pk).superseded)
            for pk in (old.pk,new.pk,approved.pk): self.assertEqual(A.objects.get(pk=pk).snapshot,snapshot)
            self.assertEqual(A.objects.get(pk=old.pk).decision,'PENDING')
            self.assertEqual(C.objects.get(pk=case.pk).status,'ACTION_COMPLETE');self.assertEqual(C.objects.get(pk=case.pk).due_date,date(2026,1,9))
            self.assertEqual(F.objects.get(pk=f.pk).file.name,'attachments/legacy/relative.txt')
        finally:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
