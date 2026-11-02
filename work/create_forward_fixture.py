import os,sys,sqlite3,json,subprocess
from pathlib import Path
root=Path('work/forward-fixture-source').resolve();root.mkdir()
source=Path('../independent-empty.sqlite3').resolve()
with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(root/'installed.sqlite3') as dst: src.backup(dst)
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings',SQLITE_PATH=str(root/'installed.sqlite3'),DB_ENGINE='sqlite',PRIVATE_MEDIA_ROOT=str(root/'media'))
import django
django.setup()
from django.contrib.auth.models import User
from pms.models import Manufacturer,MedicalDevice,UDI,CustomerComplaint,AdverseEvent
from django.utils import timezone
u=User.objects.create_user('TEST-forward-fixture')
m=Manufacturer.objects.create(name='TEST synthetic fixture')
d=MedicalDevice.objects.create(name='TEST fixture',manufacturer=m,model_number='TEST')
udi=UDI.objects.create(device=d,device_identifier='TEST-FORWARD')
c=CustomerComplaint.objects.create(device=d,udi=udi,reporter=u,title='TEST ONLY preserved',description='synthetic minimum',complaint_type='TEST',occurred_on=timezone.localdate(),is_example=True)
AdverseEvent.objects.create(complaint=c,event_type='TEST',serious=False,narrative='TEST synthetic original',outcome='TEST')
print('0012 설치 사본에 가상 사건 1건과 serious=False를 저장했습니다.')
