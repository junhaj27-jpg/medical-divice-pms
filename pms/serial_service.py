import hashlib
import secrets
import string
from uuid import UUID
from datetime import date,datetime

from django.core.exceptions import PermissionDenied,ValidationError
from django.db import connection,transaction,IntegrityError
from django.db.models import Q
from django.utils import timezone
from .gs1 import valid_gtin14,validate_gtin14
from .serial_models import GTINNamespace,ManufacturingSerial,SerialLotReference

MAX_SERIAL_ATTEMPTS=5


def authorize_device(user,device):
    from .market_service import require_workspace,scoped,product_markets
    require_workspace(user)
    if scoped(user) and not product_markets(user).filter(device_id=device.pk).exists():raise PermissionDenied


def lock_namespace(gtin):
    """Call as the first statement of the issuance transaction (SQLite write reservation)."""
    if connection.vendor=="sqlite":
        table=connection.ops.quote_name(GTINNamespace._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(f"INSERT OR IGNORE INTO {table} (gtin_14) VALUES (%s)",[gtin])
    else:
        GTINNamespace.objects.get_or_create(gtin_14=gtin)
        GTINNamespace.objects.select_for_update().get(pk=gtin)


def lot_gtin(lot):
    if valid_gtin14(lot.udi.device_identifier):return lot.udi.device_identifier
    return lot.device.gtin_14 if valid_gtin14(lot.device.gtin_14) else ""


def lot_snapshot(lot):
    return {"lot_id":lot.pk,"device_id":lot.device_id,"udi_id":lot.udi_id,
        "device_identifier":lot.udi.device_identifier,"serial_number":lot.serial_number,
        "manufactured_on":str(lot.manufactured_on or ""),"distributed_quantity":lot.distributed_quantity,
        "lot_number":lot.lot_number,"mapping_gtin":lot_gtin(lot)}


def import_lot(lot,origin="LEGACY"):
    if not lot.serial_number:return None
    gtin=lot_gtin(lot)
    # Unknown GTINs are never merged into one artificial namespace.
    previous=SerialLotReference.objects.filter(lot=lot,serial__gtin_14=gtin,serial__serial_number=lot.serial_number).select_related("serial").first()
    if previous:return previous.serial
    values=dict(device_id=lot.device_id,manufactured_on=lot.manufactured_on,origin=origin,
                is_example=lot.device.model_number.startswith("DEMO-"))
    if gtin:
        serial,_=ManufacturingSerial.objects.get_or_create(gtin_14=gtin,serial_number=lot.serial_number,defaults=values)
    else:serial=ManufacturingSerial.objects.create(gtin_14="",serial_number=lot.serial_number,**values)
    SerialLotReference.objects.get_or_create(lot=lot,serial=serial,defaults={"original":lot_snapshot(lot)})
    return serial


def sync_legacy(gtin):
    from .models import ProductLot
    for lot in ProductLot.objects.filter(Q(udi__device_identifier=gtin)|Q(device__gtin_14=gtin)).exclude(serial_number="").select_related("device","udi"):
        if lot_gtin(lot)==gtin:import_lot(lot)


def generate_serial():
    return ''.join(secrets.choice(string.ascii_uppercase+string.digits) for _ in range(10))


def constraint_kind(exc):
    name=getattr(getattr(exc.__cause__,"diag",None),"constraint_name",None)
    if name in ("manufacturing_gtin_serial_unique","manufacturing_serial_request_unique"):return name
    message=str(exc)
    table=ManufacturingSerial._meta.db_table
    if message==f"UNIQUE constraint failed: {table}.gtin_14, {table}.serial_number":return "manufacturing_gtin_serial_unique"
    if message==f"UNIQUE constraint failed: {table}.request_key":return "manufacturing_serial_request_unique"
    return None


def issue_serial(user,device,gtin_snapshot,manufactured_on,request_key):
    from .models import MedicalDevice
    from .services import audit
    authorize_device(user,device);validate_gtin14(gtin_snapshot)
    if not isinstance(manufactured_on,date) or isinstance(manufactured_on,datetime):raise ValidationError("실제 제조일을 입력하세요.")
    try:key=UUID(str(request_key))
    except (ValueError,TypeError,AttributeError):raise ValidationError("올바른 발급 요청 키가 필요합니다.")
    digest=hashlib.sha256(f"{user.pk}|{device.pk}|{gtin_snapshot}|{manufactured_on.isoformat()}".encode()).hexdigest()
    def replay(record):
        if record.issued_by_id!=user.pk or record.device_id!=device.pk:raise PermissionDenied
        if record.request_hash!=digest:raise ValidationError("같은 요청 키를 다른 발급 입력에 재사용할 수 없습니다.",code="idempotency_conflict")
        return record,False
    with transaction.atomic():
        lock_namespace(gtin_snapshot)
        device=MedicalDevice.objects.select_for_update().get(pk=device.pk)
        existing=ManufacturingSerial.objects.filter(request_key=key).first()
        if existing:return replay(existing)
        if device.gtin_14!=gtin_snapshot:raise ValidationError("제품 GTIN이 변경됐습니다. 최신 화면을 다시 열어 발급하세요.")
        sync_legacy(gtin_snapshot)
        for attempt in range(MAX_SERIAL_ATTEMPTS):
            candidate=generate_serial()
            try:
                with transaction.atomic():
                    record=ManufacturingSerial.objects.create(device=device,gtin_14=gtin_snapshot,serial_number=candidate,
                        manufactured_on=manufactured_on,issued_by=user,issued_at=timezone.now(),origin="ISSUED",request_key=key,
                        request_hash=digest,is_example=device.model_number.startswith("DEMO-"))
            except IntegrityError as exc:
                kind=constraint_kind(exc)
                if kind=="manufacturing_gtin_serial_unique":continue
                if kind=="manufacturing_serial_request_unique":return replay(ManufacturingSerial.objects.get(request_key=key))
                raise
            audit(user,"MANUFACTURING_SERIAL_ISSUE",record,after={"device_id":device.pk,"gtin":gtin_snapshot,"request_key":str(key)})
            return record,True
        raise ValidationError("제조번호 충돌 재시도 한도를 초과했습니다. 같은 요청 키로 다시 시도하세요.",code="serial_collision_exhausted")


def prepare_lot(lot):
    """Reserve new manual LOT serials too; historical duplicate import uses import_lot explicitly."""
    if not lot.serial_number:return None
    if lot.pk and lot.serial_identity_id:
        previous=lot.serial_identity
        if previous.serial_number==lot.serial_number:return previous
    gtin=lot_gtin(lot)
    if not gtin:return None
    lock_namespace(gtin)
    sync_legacy(gtin)
    existing=ManufacturingSerial.objects.filter(gtin_14=gtin,serial_number=lot.serial_number).first()
    if existing:
        if lot.pk and existing.lot_references.filter(lot_id=lot.pk).exists():return existing
        if existing.origin=="ISSUED" and existing.device_id==lot.device_id and not existing.lot_references.exists():
            if lot.manufactured_on and lot.manufactured_on!=existing.manufactured_on:raise ValidationError("발급 당시 제조일과 LOT 제조일이 다릅니다.")
            return existing
        raise ValidationError("이 GTIN에 이미 등록된 제조번호입니다. 기존 원장과 LOT를 확인하세요.")
    return ManufacturingSerial.objects.create(device=lot.device,gtin_14=gtin,serial_number=lot.serial_number,
        manufactured_on=lot.manufactured_on,origin="MANUAL",is_example=lot.device.model_number.startswith("DEMO-"))
