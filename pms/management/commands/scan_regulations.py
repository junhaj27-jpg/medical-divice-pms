from django.core.management.base import BaseCommand
from pms.models import RegulationDocument
from pms.file_security import scan_attachment
from pms.regulation_documents import extract_document
class Command(BaseCommand):
    help="규정 원본 파일 재검사 후 통과한 파일만 텍스트 추출 (격리 자동 해제 안 함)"
    def handle(self,*args,**options):
        counts={}
        for doc in RegulationDocument.objects.filter(scan_status__in=['PENDING','FAILED']).select_related('uploaded_by'):
            scan_attachment(doc)
            if doc.scan_status=='PASSED': doc=extract_document(doc,doc.uploaded_by)
            counts[doc.scan_status]=counts.get(doc.scan_status,0)+1
        self.stdout.write(str(counts))
