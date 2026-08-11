from django.core.management.base import BaseCommand
from pms.services import create_deadline_notifications
class Command(BaseCommand):
    help="처리 기한 알림 생성 (cron/Celery 없이 실행 가능)"
    def handle(self,*args,**kwargs): self.stdout.write(f"{create_deadline_notifications()}개 알림 생성")
