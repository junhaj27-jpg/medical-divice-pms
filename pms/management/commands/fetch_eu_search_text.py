from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from pms.eu_legal_models import EULegalDocument
from pms.eu_acquisition import acquire

class Command(BaseCommand):
    help='Stage verified EU HTML/PDF from official routes or a supplied official file; publish only after indexing.'
    def add_arguments(self,parser):
        parser.add_argument('--user',required=True)
        parser.add_argument('--document',required=True,type=int)
        parser.add_argument('--articles',required=True)
        parser.add_argument('--input-file',help='Official HTML/PDF; identity, language and version will be checked.')
        parser.add_argument('--source-url',help='Official URL of the imported file.')
        parser.add_argument('--op-page',help='Official Publications Office detail page for this CELEX.')
        parser.add_argument('--attempts',type=int,default=3)
    def handle(self,**options):
        try:
            user=get_user_model().objects.get(username=options['user'])
            document=EULegalDocument.objects.get(pk=options['document'])
            articles=[int(n.strip()) for n in options['articles'].split(',')]
            row,created=acquire(document,user,articles,input_file=options['input_file'],source_url=options['source_url'],op_page=options['op_page'],max_attempts=options['attempts'])
        except Exception as exc:raise CommandError(f'EU acquisition failed: {getattr(exc,"status",type(exc).__name__)}: {exc}. Existing published index retained.') from exc
        self.stdout.write(f'text_version={row.pk}; version={row.version}; created={created}; method={row.source_method}; staged until index publication')
