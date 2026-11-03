from datetime import date
from django.test import TransactionTestCase
from django.db import connection
from django.utils import timezone
from django.db.migrations.executor import MigrationExecutor

class RAForwardMigrationTests(TransactionTestCase):
    def test_existing_case_tasks_and_paths_retained_without_invented_ra_profiles(self):
        previous=('pms','0015_signal_list_query_index')
        executor=MigrationExecutor(connection);executor.migrate([previous])
        old=executor.loader.project_state([previous]).apps
        User=old.get_model('auth','User');user=User.objects.create(username='TEST-RA-migration')
        maker=old.get_model('pms','Manufacturer').objects.create(name='TEST-RA-migration')
        device=old.get_model('pms','MedicalDevice').objects.create(manufacturer=maker,name='TEST',model_number='RA')
        udi=old.get_model('pms','UDI').objects.create(device=device,device_identifier='TEST-RA-migration')
        case=old.get_model('pms','CustomerComplaint').objects.create(device=device,udi=udi,reporter=user,occurred_on=date(2026,1,1),complaint_type='TEST',title='TEST legacy',description='preserve')
        task=old.get_model('pms','WorkTask').objects.create(complaint=case,assignee=user,title='TEST task',due_at=timezone.now())
        file=old.get_model('pms','Attachment').objects.create(complaint=case,uploaded_by=user,file='attachments/existing/keep.txt')
        try:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
            from .models import Attachment,CustomerComplaint,WorkTask
            from .ra_models import RegulatoryProfile
            self.assertEqual(CustomerComplaint.objects.get(pk=case.pk).description,'preserve')
            current=Attachment.objects.get(pk=file.pk)
            self.assertEqual(current.complaint_id,case.pk);self.assertIsNone(current.ra_profile_id)
            self.assertEqual(current.file.name,'attachments/existing/keep.txt')
            current_task=WorkTask.objects.get(pk=task.pk)
            self.assertEqual(current_task.complaint_id,case.pk);self.assertIsNone(current_task.ra_profile_id)
            self.assertEqual(RegulatoryProfile.objects.count(),0)
        finally:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
