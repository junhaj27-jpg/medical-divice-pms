"""Regression checks for mutable recall metadata and server-side chronology."""
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from .tests import Base
from .models import BusinessPartner, Recall, RecallRecipient, RecallContact, WorkTask
from .workflow import save_recipient, record_recovery, record_contact, save_task


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RecallRevisionTests(Base):
    def setUp(self):
        super().setUp()
        self.today=timezone.localdate()
        self.recall=Recall.objects.create(complaint=self.complaint(),device=self.d,
            title='Recall',reason='Review',risk_level='HIGH',distributed_quantity=10,
            target_quantity=10,start_date=self.today,expected_end_date=self.today,owner=self.raqa)
        self.row=save_recipient(RecallRecipient(recall=self.recall,lot=self.lot,
            partner=BusinessPartner.objects.create(name='Partner'),target_quantity=10),self.raqa)

    def test_stale_notification_edit_preserves_atomic_counter(self):
        stale=RecallRecipient.objects.get(pk=self.row.pk)
        record_recovery(self.row,self.raqa,8,self.today)
        stale.notified_on=self.today
        save_recipient(stale,self.raqa)
        self.row.refresh_from_db()
        self.assertEqual(self.row.recovered_total,8)
        self.assertRaises(ValidationError,record_recovery,self.row,self.raqa,3,self.today)
        self.assertEqual(self.row.recovered_quantity,8)

    def test_new_recipient_cannot_forge_recovery_counter(self):
        row=RecallRecipient(recall=self.recall,lot=self.lot,
            partner=BusinessPartner.objects.create(name='Other'),target_quantity=10,recovered_total=5)
        self.assertRaises(ValidationError,save_recipient,row,self.raqa)

    def test_reply_requires_notification_date_and_reason(self):
        self.row.reply_status='REPLIED'; self.row.replied_on=self.today
        self.assertRaises(ValidationError,save_recipient,self.row,self.raqa)
        self.row.notified_on=self.today; self.row.replied_on=self.today-timedelta(days=1)
        self.assertRaises(ValidationError,save_recipient,self.row,self.raqa)
        self.row.replied_on=self.today; self.row.reply_status='DECLINED'
        self.assertRaises(ValidationError,save_recipient,self.row,self.raqa)
        self.row.unrecovered_reason='Disposed by partner'; save_recipient(self.row,self.raqa)

    def test_future_recovery_rolls_back_counter(self):
        self.assertRaises(ValidationError,record_recovery,self.row,self.raqa,1,self.today+timedelta(days=1))
        self.row.refresh_from_db(); self.assertEqual(self.row.recovered_total,0)
        self.assertEqual(self.row.recoveries.count(),0)

    def test_future_contact_is_form_error(self):
        self.client.force_login(self.raqa)
        response=self.client.post(reverse('contact-create',args=[self.row.pk]),{
            'contacted_at':(timezone.localtime()+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
            'method':'전화','note':'확인'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'현재 또는 과거')
        self.assertFalse(self.row.contacts.exists())

    def test_recovery_post_retry_creates_single_ledger_entry(self):
        self.client.force_login(self.raqa)
        url=reverse('recovery-create',args=[self.row.pk])
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        token=response.context['form']['submission_key'].value()
        self.assertTrue(token)
        data={'quantity':3,'recovered_on':self.today.isoformat(),'submission_key':str(token)}
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.recovered_total,3)
        self.assertEqual(self.row.recoveries.count(),1)
        data['quantity']=4
        self.assertContains(self.client.post(url,data),'이미 사용한 회수 등록 키')
        self.row.refresh_from_db(); self.assertEqual(self.row.recovered_total,3)

    def test_recovery_post_requires_submission_key(self):
        self.client.force_login(self.raqa)
        response=self.client.post(reverse('recovery-create',args=[self.row.pk]),{
            'quantity':3,'recovered_on':self.today.isoformat()})
        self.assertEqual(response.status_code,200)
        self.assertFalse(self.row.recoveries.exists())

    def test_completion_time_is_preserved_and_reopening_is_privileged(self):
        task=save_task(WorkTask(complaint=self.recall.complaint,assignee=self.staff,
            title='Task',due_at=timezone.now()),self.raqa)
        self.assertIsNone(task.completed_at)
        task.status='DONE'; save_task(task,self.staff); completed=task.completed_at
        save_task(task,self.staff); self.assertEqual(task.completed_at,completed)
        task.status='IN_PROGRESS'
        self.assertRaises(ValidationError,save_task,task,self.staff)
        save_task(task,self.raqa); self.assertIsNone(task.completed_at)
        self.assertEqual(task.history.order_by('pk').last().before['completed_at'],completed.isoformat())

    def test_task_missing_deadline_is_validation_error(self):
        task=WorkTask(complaint=self.recall.complaint,assignee=self.staff,title='Task')
        self.assertRaises(ValidationError,save_task,task,self.raqa)
        self.assertIsNone(task.pk)
