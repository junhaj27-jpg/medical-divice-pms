from datetime import date,datetime,timezone
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

class LegacyRegulationMigrationTests(TransactionTestCase):
    def test_old_rules_and_case_applications_are_preserved(self):
        previous=('pms','0006_alter_reportingrule_conditions')
        latest=('pms','0008_analysisimport_analysisrecord_analysisreview_and_more')
        executor=MigrationExecutor(connection);executor.migrate([previous])
        try:
            old=executor.loader.project_state([previous]).apps
            User=old.get_model('auth','User');Manufacturer=old.get_model('pms','Manufacturer');Device=old.get_model('pms','MedicalDevice');UDI=old.get_model('pms','UDI');Complaint=old.get_model('pms','CustomerComplaint');Rule=old.get_model('pms','ReportingRule');Application=old.get_model('pms','RuleApplication')
            user=User.objects.create(username='migration-user');manufacturer=Manufacturer.objects.create(name='migration fixture');device=Device.objects.create(name='test',model_number='migration',manufacturer=manufacturer);udi=UDI.objects.create(device=device,device_identifier='MIGRATION-TEST')
            case=Complaint.objects.create(device=device,udi=udi,complaint_type='TEST',title='migration test',description='synthetic test',occurred_on=date(2026,1,1),reporter=user,due_date=date(2026,1,7))
            first=Rule.objects.create(name='legacy A',version=1,basis='REPORTED',days=3,day_type='CALENDAR',effective_on=date(2026,1,1),change_reason='old')
            second=Rule.objects.create(name='legacy A',version=2,basis='REPORTED',days=5,day_type='CALENDAR',effective_on=date(2026,2,1),change_reason='old')
            third=Rule.objects.create(name='legacy B',version=1,basis='OCCURRED',days=2,day_type='BUSINESS',holidays=['2026-01-02'],effective_on=date(2026,1,1),change_reason='old')
            snapshot={'original':'keep byte-equivalent JSON data','days':3};due=datetime(2026,1,7,14,59,tzinfo=timezone.utc)
            app=Application.objects.create(complaint=case,rule=first,snapshot=snapshot,due_at=due,actor=user,reason='original applied reason')
            executor=MigrationExecutor(connection);executor.migrate([latest]);new=executor.loader.project_state([latest]).apps
            NewRule=new.get_model('pms','ReportingRule');NewApp=new.get_model('pms','RuleApplication');NewCase=new.get_model('pms','CustomerComplaint')
            a=NewRule.objects.get(pk=first.pk);b=NewRule.objects.get(pk=second.pk);c=NewRule.objects.get(pk=third.pk)
            self.assertEqual((a.state,b.state,c.state),('LEGACY','LEGACY','LEGACY'));self.assertEqual(a.family_key,b.family_key);self.assertNotEqual(a.family_key,c.family_key)
            self.assertEqual((a.days,b.days,c.holidays),(3,5,['2026-01-02']))
            applied=NewApp.objects.get(pk=app.pk);self.assertEqual(applied.snapshot,snapshot);self.assertEqual(applied.due_at,due);self.assertEqual(applied.reason,'original applied reason');self.assertEqual(NewCase.objects.get(pk=case.pk).due_date,date(2026,1,7))
        finally:
            MigrationExecutor(connection).migrate([latest])
