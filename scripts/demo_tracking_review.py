"""Create synthetic tracking/PDF demo in a NEW isolated directory only."""
import os
import sys
import uuid
from pathlib import Path

target=Path(sys.argv[1]).resolve()
if target.exists(): raise SystemExit('새 디렉터리를 지정하세요. 기존 DB는 수정하지 않습니다.')
password=os.environ.get('DEMO_PASSWORD')
if not password: raise SystemExit('DEMO_PASSWORD를 지정하세요.')
target.mkdir(parents=True)
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings',DB_ENGINE='sqlite',SQLITE_PATH=str(target/'demo.sqlite3'),PRIVATE_MEDIA_ROOT=str(target/'media'))
import django
django.setup()
from django.core.management import call_command
from django.contrib.auth.models import User
from pms.models import Profile, MedicalDevice
from pms.safety import SafetyFilter, detect
from pms.signal_tracking import track_signal
from pms.periodic import create_periodic, finalize_periodic
call_command('migrate',interactive=False,verbosity=0)
users={}
for name,role in [('demo-staff','STAFF'),('demo-raqa','RA_QA'),('demo-admin','ADMIN')]:
    user=User.objects.create_user(name,password=password)
    Profile.objects.create(user=user,role=role);users[role]=user
call_command('seed_safety_demo',reporter='demo-staff',as_of='2026-10-28')
ra=users['RA_QA']
form=SafetyFilter(ra,dict(start='2026-10-01',end='2026-10-28',example='sample',interval='week'))
if not form.is_valid(): raise SystemExit(str(form.errors))
signals=detect(ra,form.cleaned_data)
signal=signals[0]
def payload(**kw): return dict(request_key=str(uuid.uuid4()),**kw)
track_signal(ra,signal.pk,payload(kind='INVESTIGATE',note='격리 예시 조사',basis='예시 발생 건수 확인',due_on='2026-12-01'))
track_signal(ra,signal.pk,payload(kind='HOLD',note='추가 조사 필요 - 예시'))
draft=create_periodic(ra,payload(device=signal.snapshot['group']['device_id'],start='2026-10-01',end='2026-10-28',is_example=True))
final=finalize_periodic(users['ADMIN'],draft.pk,payload(review_note='격리 예시 검토 완료',confirm=True))
(target/'periodic-review.pdf').write_bytes(bytes(final.pdf_content))
print(f'Signal: /safety/signals/{signal.pk}/tracking/ | Review: /pms-reviews/{final.pk}/')
print(f'DB: {target / "demo.sqlite3"}')
