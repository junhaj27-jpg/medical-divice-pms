from datetime import date
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class SerialMigrationTests(TransactionTestCase):
    def test_legacy_duplicate_and_unknown_gtin_preserved(self):
        previous=('pms','0047_registered_mri_template')
        executor=MigrationExecutor(connection);executor.migrate([previous])
        apps=executor.loader.project_state([previous]).apps
        maker=apps.get_model('pms','Manufacturer').objects.create(name='DEMO migration')
        device=apps.get_model('pms','MedicalDevice').objects.create(name='DEMO',model_number='DEMO-MIGRATION',manufacturer=maker)
        udi=apps.get_model('pms','UDI').objects.create(device=device,device_identifier='09506000134352')
        unknown=apps.get_model('pms','UDI').objects.create(device=device,device_identifier='NOT-A-GTIN')
        Lot=apps.get_model('pms','ProductLot')
        lots=[Lot.objects.create(device=device,udi=udi,lot_number=str(i),serial_number='KEEP-ME',manufactured_on=date(2026,11,13),distributed_quantity=i) for i in (1,2)]
        unmapped=Lot.objects.create(device=device,udi=unknown,lot_number='unknown',serial_number='KEEP-UNKNOWN')
        original=list(Lot.objects.values('pk','serial_number','manufactured_on','distributed_quantity'))
        try:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
            from .models import ProductLot
            from .serial_models import ManufacturingSerial
            self.assertEqual(list(ProductLot.objects.values('pk','serial_number','manufactured_on','distributed_quantity')),original)
            serial=ManufacturingSerial.objects.get(gtin_14='09506000134352',serial_number='KEEP-ME')
            self.assertEqual(set(serial.lot_references.values_list('lot_id',flat=True)),{lot.pk for lot in lots})
            self.assertIsNone(serial.issued_at);self.assertIsNone(serial.issued_by_id)
            self.assertEqual(serial.expected_udi,'');self.assertIn('중복',serial.status)
            self.assertEqual(ProductLot.objects.get(pk=unmapped.pk).serial_identity.gtin_14,'')
        finally:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
