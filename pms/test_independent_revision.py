"""Independent adversarial regression checks for the October workflow revision."""
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from .tests import Base
from .models import CAPA, Recall, RecallRecipient, BusinessPartner, WorkTask
from .workflow import save_task, save_recipient, record_recovery, recall_totals
from .file_security import validate_upload
from .reporting import snapshot_case


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class IndependentWorkflowRevisionTests(Base):
    def setUp(self):
        super().setUp()
        self.case = self.complaint()
        self.capa = CAPA.objects.create(complaint=self.case, title='independent CAPA', corrective_action='action', owner=self.raqa, due_date=timezone.localdate())
        self.recall = Recall.objects.create(complaint=self.case, title='independent recall', reason='test', device=self.d, risk_level='HIGH', distributed_quantity=10, target_quantity=10, start_date=timezone.localdate(), expected_end_date=timezone.localdate(), owner=self.raqa)
        self.partner = BusinessPartner.objects.create(name='independent partner')

    def recipient(self, **changes):
        data = dict(recall=self.recall, lot=self.lot, partner=self.partner, target_quantity=10)
        data.update(changes)
        return save_recipient(RecallRecipient(**data), self.raqa)

    def test_anonymous_and_staff_cannot_mutate_privileged_workflows(self):
        row = self.recipient()
        urls = [reverse('capa-evaluate', args=[self.capa.pk]), reverse('capa-close', args=[self.capa.pk]), reverse('recipient-create', args=[self.recall.pk]), reverse('recovery-create', args=[row.pk]), reverse('contact-create', args=[row.pk]), reverse('artifact-generate', args=[self.case.pk])]
        for url in urls:
            self.assertEqual(self.client.post(url, {}).status_code, 302, url)
        self.client.force_login(self.other)
        for url in urls:
            self.assertEqual(self.client.post(url, {}).status_code, 403, url)
        self.assertEqual(self.capa.evaluations.count(), 0)
        self.assertEqual(row.recoveries.count(), 0)
        self.assertEqual(self.case.artifacts.count(), 0)

    def test_invalid_recovery_types_dates_and_quantities_do_not_reserve_capacity(self):
        row = self.recipient()
        for value in (0, -1, True, 1.5, '2', 11):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                record_recovery(row, self.raqa, value, timezone.localdate())
        with self.assertRaises(ValidationError):
            record_recovery(row, self.raqa, 1, timezone.localdate() + timedelta(days=1))
        row.refresh_from_db()
        self.assertEqual(row.recovered_total, 0)
        self.assertEqual(row.recoveries.count(), 0)

    def test_recipient_duplicate_and_zero_target_rejected(self):
        self.recipient()
        with self.assertRaises(ValidationError):
            self.recipient()
        with self.assertRaises(ValidationError):
            self.recipient(unit='box', target_quantity=0)
        self.assertEqual(self.recall.recipients.count(), 1)

    def test_empty_ledger_and_snapshot_match_stored_partial_recovery(self):
        self.assertEqual(recall_totals(self.recall), {})
        row = self.recipient()
        record_recovery(row, self.raqa, 3, timezone.localdate())
        data = snapshot_case(self.case)['recalls'][0]
        self.assertEqual(data['totals']['개'], {'target':10, 'recovered':3, 'remaining':7})
        self.assertEqual(data['recipients'][0]['recoveries'][0]['quantity'], 3)

    def test_foreign_staff_cannot_get_or_post_task(self):
        task = save_task(WorkTask(complaint=self.case, assignee=self.staff, title='private', due_at=timezone.now()), self.raqa)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('task-detail', args=[task.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('task-edit', args=[task.pk]), {'status':'DONE'}).status_code, 404)
        task.refresh_from_db()
        self.assertEqual(task.status, 'WAITING')

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=4)
    def test_evidence_empty_and_oversize_rejected(self):
        for payload in (b'', b'12345'):
            with self.assertRaises(ValidationError):
                validate_upload(SimpleUploadedFile('evidence.txt', payload))

class IndependentWorkflowMigrationTests(TransactionTestCase):
    def test_legacy_completed_task_and_recovery_survive_new_fields(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        previous = ('pms', '0011_merge_workflow_branches')
        executor = MigrationExecutor(connection)
        executor.migrate([previous])
        try:
            apps = executor.loader.project_state([previous]).apps
            User = apps.get_model('auth', 'User')
            actor = User.objects.create(username='independent-migration')
            maker = apps.get_model('pms', 'Manufacturer').objects.create(name='migration maker')
            device = apps.get_model('pms', 'MedicalDevice').objects.create(name='migration', model_number='m', manufacturer=maker)
            udi = apps.get_model('pms', 'UDI').objects.create(device=device, device_identifier='INDEPENDENT-MIGRATION')
            lot = apps.get_model('pms', 'ProductLot').objects.create(device=device, udi=udi, lot_number='migration')
            case = apps.get_model('pms', 'CustomerComplaint').objects.create(device=device, udi=udi, reporter=actor, title='preserve', description='synthetic', complaint_type='TEST', occurred_on=timezone.localdate())
            task = apps.get_model('pms', 'WorkTask').objects.create(complaint=case, assignee=actor, title='legacy done', due_at=timezone.now(), status='DONE')
            recall = apps.get_model('pms', 'Recall').objects.create(complaint=case, device=device, owner=actor, title='legacy', reason='test', risk_level='HIGH', distributed_quantity=5, target_quantity=5, start_date=timezone.localdate(), expected_end_date=timezone.localdate())
            partner = apps.get_model('pms', 'BusinessPartner').objects.create(name='legacy partner')
            recipient = apps.get_model('pms', 'RecallRecipient').objects.create(recall=recall, lot=lot, partner=partner, target_quantity=5, recovered_total=2)
            entry = apps.get_model('pms', 'RecoveryEntry').objects.create(recipient=recipient, actor=actor, quantity=2, recovered_on=timezone.localdate())
            executor = MigrationExecutor(connection)
            leaves = executor.loader.graph.leaf_nodes()
            executor.migrate(leaves)
            current = executor.loader.project_state(leaves).apps
            migrated = current.get_model('pms', 'WorkTask').objects.get(pk=task.pk)
            self.assertEqual(migrated.status, 'DONE')
            self.assertIsNone(migrated.completed_at)
            recovery = current.get_model('pms', 'RecoveryEntry').objects.get(pk=entry.pk)
            self.assertEqual(recovery.quantity, 2)
            self.assertIsNone(recovery.submission_key)
            self.assertEqual(current.get_model('pms', 'RecallRecipient').objects.get(pk=recipient.pk).recovered_total, 2)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())


