from django.test import override_settings
from django.utils import timezone
from .tests import Base
from .models import CAPA, WorkTask
from .reporting import snapshot_case
from .workflow import save_task
from .services import request_complaint_approval, decide_approval


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ReportRevisionTests(Base):
    def test_snapshot_preserves_completion_actions_and_review(self):
        case = self.complaint()
        case.status = 'APPROVAL'
        case.save()
        task = save_task(WorkTask(complaint=case, assignee=self.raqa,
            title='Review', due_at=timezone.now(), status='DONE'), self.raqa)
        CAPA.objects.create(complaint=case, title='CAPA', root_cause='원인',
            corrective_action='시정', preventive_action='예방', owner=self.raqa,
            due_date=timezone.localdate())
        approval = request_complaint_approval(case, self.raqa)
        decide_approval(approval, self.admin, 'APPROVED', '검토 완료')
        snapshot = snapshot_case(case)
        self.assertEqual(snapshot['selection']['complaint_id'], case.pk)
        self.assertEqual(snapshot['tasks'][0]['completed_at'], str(task.completed_at))
        self.assertEqual(snapshot['capas'][0]['root_cause'], '원인')
        self.assertEqual(snapshot['capas'][0]['corrective_action'], '시정')
        self.assertEqual(snapshot['approvals'][0]['reason'], '검토 완료')
        self.assertEqual(snapshot['approvals'][0]['decided_by__username'], self.admin.username)
        task.title = 'changed'
        task.save()
        self.assertEqual(snapshot['tasks'][0]['title'], 'Review')
