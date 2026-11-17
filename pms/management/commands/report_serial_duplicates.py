import json
from collections import defaultdict
from django.core.management.base import BaseCommand
from pms.models import ProductLot
from pms.serial_service import lot_gtin
from pms.serial_models import ManufacturingSerial
from django.db.models import Count


class Command(BaseCommand):
    help='Read-only report of legacy GTIN/serial duplicates and unresolved GTIN lot IDs.'
    def handle(self,**options):
        groups=defaultdict(list); unknown=[]
        for lot in ProductLot.objects.exclude(serial_number='').select_related('device','udi'):
            gtin=lot_gtin(lot)
            if gtin:groups[(gtin,lot.serial_number)].append(lot.pk)
            else:unknown.append(lot.pk)
        historical=[]
        for serial in ManufacturingSerial.objects.exclude(gtin_14='').annotate(references=Count('lot_references')).filter(references__gt=1):
            historical.append(dict(gtin=serial.gtin_14,serial=serial.serial_number,registry_id=serial.pk,lot_ids=list(serial.lot_references.values_list('lot_id',flat=True))))
        self.stdout.write(json.dumps({'duplicates':[dict(gtin=g,serial=s,lot_ids=ids) for (g,s),ids in groups.items() if len(ids)>1],
            'historical_duplicates':historical,'gtin_unspecified_lot_ids':unknown},ensure_ascii=False,indent=2))
