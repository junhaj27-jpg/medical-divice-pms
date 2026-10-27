from django.core.management.base import BaseCommand
from pms.backup import backup
class Command(BaseCommand):
    help="서비스 중지 후 DB·비공개 미디어 백업 (SQLite / PostgreSQL)"
    def add_arguments(self,parser):
        parser.add_argument("destination")
        parser.add_argument("--quiesced",action="store_true")
    def handle(self,*args,**options):
        result=backup(options["destination"],options["quiesced"])
        self.stdout.write(self.style.SUCCESS(f"백업 완료: {len(result)}개 파일"))
