from django.core.management.base import BaseCommand
from pms.workflow import notify_tasks
class Command(BaseCommand):
    help="담당 업무 임박·초과 내부 알림 (중복 방지)"
    def handle(self,*args,**options): self.stdout.write(str(notify_tasks()))
