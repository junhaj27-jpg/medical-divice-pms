from django.db import migrations
import re


def import_serials(apps, schema_editor):
    Lot=apps.get_model('pms','ProductLot'); Serial=apps.get_model('pms','ManufacturingSerial')
    Ref=apps.get_model('pms','SerialLotReference')
    def valid(s):
        return bool(re.fullmatch('[0-9]{14}',s)) and int(s[-1])==(10-sum(int(c)*(3 if i%2==0 else 1) for i,c in enumerate(reversed(s[:13])))%10)%10
    for lot in Lot.objects.exclude(serial_number='').select_related('udi','device').iterator():
        raw=lot.udi.device_identifier
        gtin=raw if valid(raw) else lot.device.gtin_14 if valid(lot.device.gtin_14) else ''
        defaults=dict(device_id=lot.device_id,manufactured_on=lot.manufactured_on,origin='LEGACY',is_example=lot.device.model_number.startswith('DEMO-'))
        if gtin: serial,_=Serial.objects.get_or_create(gtin_14=gtin,serial_number=lot.serial_number,defaults=defaults)
        else: serial=Serial.objects.create(gtin_14='',serial_number=lot.serial_number,**defaults)
        Ref.objects.create(serial_id=serial.pk,lot_id=lot.pk,original=dict(lot_id=lot.pk,device_id=lot.device_id,udi_id=lot.udi_id,device_identifier=raw,serial_number=lot.serial_number,manufactured_on=str(lot.manufactured_on or ''),distributed_quantity=lot.distributed_quantity,lot_number=lot.lot_number,mapping_gtin=gtin))
        Lot.objects.filter(pk=lot.pk).update(serial_identity_id=serial.pk)


class Migration(migrations.Migration):
    dependencies=[('pms','0048_manufacturing_serials')]
    operations=[migrations.RunPython(import_serials,migrations.RunPython.noop)]
