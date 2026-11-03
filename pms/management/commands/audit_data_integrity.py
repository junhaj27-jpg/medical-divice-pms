import json
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from pms.migrations._integrity_preflight import violations

class Command(BaseCommand):
    help='Read-only integrity preflight; emits model, primary key and rule, never narratives.'
    def add_arguments(self,parser): parser.add_argument('--database',default='default')
    def handle(self,*args,**options):
        issues=violations(apps,options['database'])
        self.stdout.write(json.dumps({'violations':issues,'count':len(issues)},ensure_ascii=False,indent=2))
        if issues: raise CommandError('Integrity violations require reviewed correction before migration.')
