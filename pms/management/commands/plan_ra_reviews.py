from datetime import date
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from django.core.exceptions import ValidationError,PermissionDenied
from pms.ra_services import plan_due_reviews

class Command(BaseCommand):
    help='명시된 RA 검토·갱신·교육 기한만 기존 업무/내부 알림으로 생성 (외부 발송 없음)'
    def add_arguments(self,parser):
        parser.add_argument('--actor',required=True,help='실제 실행 RA/QA 또는 ADMIN 사용자명')
        parser.add_argument('--as-of',type=date.fromisoformat)
        parser.add_argument('--horizon-days',type=int,default=30)
    def handle(self,*args,**options):
        try:
            user=get_user_model().objects.get(username=options['actor'])
            tasks=plan_due_reviews(user,options['as_of'],options['horizon_days'])
        except (get_user_model().DoesNotExist,ValidationError,PermissionDenied) as exc: raise CommandError(str(exc))
        self.stdout.write(f'기존 업무 {len(set(task.pk for task in tasks))}개 확인·생성. 만료일·검토주기를 추정하지 않았습니다.')
