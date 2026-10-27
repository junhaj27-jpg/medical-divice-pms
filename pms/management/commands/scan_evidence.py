from django.core.management.base import BaseCommand
from pms.models import Attachment
from pms.file_security import scan_attachment
class Command(BaseCommand):
    help="검사 대기·실패 증빙 재검사 (외부 발송 없음)"
    def handle(self,*args,**options):
        counts={}
        for obj in Attachment.objects.filter(scan_status__in=["PENDING","FAILED"]):
            scan_attachment(obj); counts[obj.scan_status]=counts.get(obj.scan_status,0)+1
        self.stdout.write(str(counts))
