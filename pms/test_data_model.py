from datetime import date
from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .tests import Base
from .models import *
from .workflow import record_recovery, save_recipient
from .services import request_complaint_approval
from .approval_integrity import approval_invalid_reason
from .migrations._integrity_preflight import violations

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DataModelTests(Base):
    def setUp(self):
        super().setUp()
        self.case=self.complaint()
        self.other_device=MedicalDevice.objects.create(manufacturer=self.m,name='other',model_number='2')
        self.other_udi=UDI.objects.create(device=self.other_device,device_identifier='OTHER')
    def recall(self):
        return Recall.objects.create(complaint=self.case,device=self.d,title='test',reason='test',risk_level='LOW',distributed_quantity=10,target_quantity=5,start_date=timezone.localdate(),expected_end_date=timezone.localdate(),owner=self.raqa)
    def risk(self):
        risk=RiskAssessment(complaint=self.case,severity=2,probability=2,assessed_by=self.raqa)
        risk._history_actor=self.raqa;risk.save();return risk
    def test_direct_orm_relationships_and_inverse_reparent(self):
        self.assertRaises(ValidationError,ProductLot.objects.create,device=self.other_device,udi=self.udi,lot_number='bad')
        self.case.udi=self.other_udi;self.assertRaises(ValidationError,self.case.save)
        self.udi.device=self.other_device;self.assertRaises(ValidationError,self.udi.save)
    def test_same_device_different_udi_lot_rejected(self):
        udi=UDI.objects.create(device=self.d,device_identifier='SAME-DEVICE')
        self.case.udi=udi;self.assertRaises(ValidationError,self.case.save)
    def test_partial_api_update_cannot_bypass_product_check(self):
        api=APIClient();api.force_authenticate(self.raqa)
        response=api.patch(f'/api/complaints/{self.case.pk}/',{'udi':self.other_udi.pk},format='json')
        self.assertEqual(response.status_code,400)
        self.case.refresh_from_db();self.assertEqual(self.case.udi_id,self.udi.pk)
    def test_patient_and_inverse_case(self):
        foreign=self.complaint(self.other)
        patient=PatientAnonymousInfo.objects.create(complaint=foreign,anonymous_code='anonymous-test')
        self.assertRaises(ValidationError,AdverseEvent.objects.create,complaint=self.case,patient=patient,event_type='test',outcome='test',narrative='test')
        event=AdverseEvent.objects.create(complaint=foreign,patient=patient,event_type='test',outcome='test',narrative='test')
        patient.complaint=self.case;self.assertRaises(ValidationError,patient.save)
    def test_database_domains_quantity_and_score(self):
        risk=self.risk();recall=self.recall()
        for qs,data in [(CustomerComplaint.objects.filter(pk=self.case.pk),{'status':'INVALID'}),(RiskAssessment.objects.filter(pk=risk.pk),{'severity':6}),(RiskAssessment.objects.filter(pk=risk.pk),{'score':24}),(Recall.objects.filter(pk=recall.pk),{'target_quantity':11}),(Recall.objects.filter(pk=recall.pk),{'recovered_quantity':6})]:
            with self.assertRaises(IntegrityError),transaction.atomic(): qs.update(**data)
    def test_target_duplicate_and_total_capacity(self):
        recall=self.recall()
        RecallTarget.objects.create(recall=recall,lot=self.lot,target_quantity=3)
        self.assertRaises(ValidationError,RecallTarget.objects.create,recall=recall,lot=self.lot,serial_number='another',target_quantity=3)
        with self.assertRaises(IntegrityError),transaction.atomic():
            RecallTarget.objects.create(recall=recall,lot=self.lot,target_quantity=1)
    def test_recall_and_task_mismatch_and_inactive(self):
        recall=self.recall();recall.device=self.other_device;self.assertRaises(ValidationError,recall.save)
        self.other.is_active=False;self.other.save()
        self.assertRaises(ValidationError,WorkTask.objects.create,complaint=self.case,assignee=self.other,title='bad',due_at=timezone.now())
    def test_evidence_and_actor_deletion_protected(self):
        risk=self.risk()
        self.assertRaises(ProtectedError,self.case.delete)
        self.assertRaises(ProtectedError,self.raqa.delete)
        self.assertRaises(ProtectedError,risk.delete)
    def test_history_snapshot_survives_current_edit(self):
        risk=self.risk();original=risk.history.get();old=original.after.copy()
        risk.rationale='new reason';risk._history_actor=self.admin;risk.save()
        original.refresh_from_db();self.assertEqual(original.after,old)
        latest=risk.history.last();self.assertEqual(latest.actor,self.admin)
        self.assertEqual(latest.before['rationale'],'');self.assertEqual(latest.after['rationale'],'new reason')
        self.assertRaises(ValidationError,original.save)
        self.assertRaises(ValidationError,risk.history.all().delete)
    def test_report_and_risk_history_invalidate_approval_schema(self):
        risk=self.risk();self.case.status='APPROVAL';self.case.save()
        approval=request_complaint_approval(self.case,self.raqa)
        self.assertEqual(approval.snapshot['schema'],2)
        legacy=Approval(snapshot=dict(approval.snapshot,schema=1))
        self.assertTrue(approval_invalid_reason(legacy,self.case))
        risk.rationale='changed';risk.save();self.assertTrue(approval_invalid_reason(approval,self.case))
        report=RegulatoryReport.objects.create(complaint=self.case,author=self.raqa,document_number='history-test')
        snapshot=report.history.get().after.copy();report.status='SUBMITTED';report.save()
        self.assertEqual(report.history.count(),2);self.assertEqual(report.history.first().after,snapshot)
    def test_recovery_only_through_atomic_service(self):
        row=save_recipient(RecallRecipient(recall=self.recall(),lot=self.lot,partner=BusinessPartner.objects.create(name='test partner'),target_quantity=5),self.raqa)
        self.assertRaises(ValidationError,RecoveryEntry.objects.create,recipient=row,quantity=1,recovered_on=timezone.localdate(),actor=self.raqa)
        entry=record_recovery(row,self.raqa,3,timezone.localdate())
        self.assertRaises(ValidationError,record_recovery,row,self.raqa,3,timezone.localdate())
        row.refresh_from_db();self.assertEqual(row.recovered_total,3);self.assertEqual(row.recovered_quantity,3)
        entry.quantity=1;self.assertRaises(ValidationError,entry.save)
        self.assertRaises(ValidationError,RecoveryEntry.objects.all().delete)
    def test_recovery_retry_key_does_not_double_count(self):
        row=save_recipient(RecallRecipient(recall=self.recall(),lot=self.lot,partner=BusinessPartner.objects.create(name='retry partner'),target_quantity=5),self.raqa)
        first=record_recovery(row,self.raqa,2,timezone.localdate(),request_key='retry-1')
        second=record_recovery(row,self.raqa,2,timezone.localdate(),request_key='retry-1')
        self.assertEqual(first.pk,second.pk)
        row.refresh_from_db();self.assertEqual(row.recovered_total,2);self.assertEqual(row.recoveries.count(),1)
        self.assertRaises(ValidationError,record_recovery,row,self.raqa,3,timezone.localdate(),request_key='retry-1')

    def test_preflight_identifies_without_repair(self):
        CustomerComplaint.objects.filter(pk=self.case.pk).update(udi=self.other_udi)
        issues=violations(apps,'default')
        self.assertIn({'model':'CustomerComplaint','pk':self.case.pk,'rule':'device_udi_match'},issues)
        self.case.refresh_from_db();self.assertEqual(self.case.udi_id,self.other_udi.pk)

class IntegrityMigrationTests(TransactionTestCase):
    def test_existing_schema_forward_and_block_invalid_data(self):
        previous=('pms','0011_merge_model_branches')
        executor=MigrationExecutor(connection);executor.migrate([previous])
        old=executor.loader.project_state([previous]).apps
        user=old.get_model('auth','User').objects.create(username='migration-integrity')
        maker=old.get_model('pms','Manufacturer').objects.create(name='migration-integrity')
        device=old.get_model('pms','MedicalDevice').objects.create(manufacturer=maker,name='test',model_number='x')
        udi=old.get_model('pms','UDI').objects.create(device=device,device_identifier='migration-integrity')
        case=old.get_model('pms','CustomerComplaint').objects.create(device=device,udi=udi,reporter=user,occurred_on=date(2026,1,1),title='legacy',description='retain',complaint_type='test')
        Risk=old.get_model('pms','RiskAssessment')
        risk=Risk.objects.create(complaint=case,severity=6,probability=1,score=6,level='MEDIUM',assessed_by=user)
        try:
            executor=MigrationExecutor(connection)
            with self.assertRaisesMessage(RuntimeError,'risk_values_range'):
                executor.migrate(executor.loader.graph.leaf_nodes())
            self.assertEqual(Risk.objects.get(pk=risk.pk).severity,6)
            # Explicit fixture correction represents an operator-reviewed correction, never migration repair.
            Risk.objects.filter(pk=risk.pk).update(severity=3,score=3,level='LOW')
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
            self.assertEqual(CustomerComplaint.objects.get(pk=case.pk).description,'retain')
            self.assertEqual(RiskAssessmentHistory.objects.count(),0)
            self.assertEqual(RiskAssessment.objects.get(pk=risk.pk).severity,3)
        finally:
            Risk.objects.filter(pk=risk.pk).update(severity=3,score=3,level='LOW')
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
