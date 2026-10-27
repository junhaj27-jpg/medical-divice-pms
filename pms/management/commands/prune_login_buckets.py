from django.core.management.base import BaseCommand
from django.utils import timezone
from pms.models import LoginBucket
class Command(BaseCommand):
    help="만료된 로그인 시도 카운터 삭제 (일일 실행 권장)"
    def handle(self,*args,**options):
        count,_=LoginBucket.objects.filter(expires_at__lt=timezone.now()).delete()
        self.stdout.write(str(count))
