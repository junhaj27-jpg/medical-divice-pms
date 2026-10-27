from django.core.management.base import BaseCommand
from pms.backup import restore_verify
class Command(BaseCommand):
    help="새 격리 디렉터리에만 복구하고 DB·파일 일치 검증"
    def add_arguments(self,parser):
        parser.add_argument("archive")
        parser.add_argument("destination")
    def handle(self,*args,**options):
        result=restore_verify(options["archive"],options["destination"])
        self.stdout.write(self.style.SUCCESS(f"격리 복구 검증 완료: {len(result['files'])}개 파일"))
