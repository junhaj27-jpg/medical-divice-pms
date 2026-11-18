import json
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from pms.source_search import index_sources


class Command(BaseCommand):
    help='Incrementally index authorized, versioned FDA/EU source text; never update PMS rules.'
    def add_arguments(self,parser):
        parser.add_argument('--user',required=True)
        parser.add_argument('--lexical-only',action='store_true')
        parser.add_argument('--jurisdiction',default='')
        parser.add_argument('--edition',default='')
    def handle(self,**options):
        try:
            user=get_user_model().objects.get(username=options['user'])
            result=index_sources(user,lexical_only=options['lexical_only'],jurisdiction=options['jurisdiction'],edition=options['edition'])
        except Exception as exc:raise CommandError(f'색인 실패: {type(exc).__name__}: {exc}') from exc
        self.stdout.write(json.dumps(result,ensure_ascii=False))
