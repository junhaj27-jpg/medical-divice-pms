"""Isolated synthetic demonstration. No provider, no antivirus bypass, no live DB."""
import os
import sys
from pathlib import Path

target=Path(sys.argv[1]).resolve()
if target.exists(): raise SystemExit("Use a NEW directory; existing data is never overwritten.")
target.mkdir(parents=True)
repo=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(repo))
os.environ["DJANGO_SETTINGS_MODULE"]="config.settings"
os.environ["SQLITE_PATH"]=str(target/"sample.sqlite3")
os.environ["PRIVATE_MEDIA_ROOT"]=str(target/"media")
import django
django.setup()
from django.core.management import call_command
from django.contrib.auth.models import User
from django.test import Client
from datetime import date
from pms.models import Profile
from pms.safety import SafetyFilter, analyze_safety, detect
call_command("migrate",interactive=False,verbosity=0)
staff=User.objects.create_user("synthetic-staff")
ra=User.objects.create_user("synthetic-reviewer")
Profile.objects.create(user=staff,role="STAFF")
Profile.objects.create(user=ra,role="RA_QA")
call_command("seed_safety_demo",reporter=staff.username,as_of="2026-10-28")
call_command("seed_safety_demo",reporter=staff.username,as_of="2026-10-28")
params=dict(start="2026-10-01",end="2026-10-28",example="sample",interval="week")
form=SafetyFilter(ra,params);assert form.is_valid(),form.errors
result=analyze_safety(ra,form.cleaned_data)
assert result["total"]==7 and result["previous_total"]==1 and result["rate"] is None
signals=detect(ra,form.cleaned_data)
assert len(signals)==2
assert [s.pk for s in detect(ra,form.cleaned_data)]==[s.pk for s in signals]
client=Client();client.force_login(ra)
response=client.get("/safety/",params);assert response.status_code==200
(target/"safety-rendered.html").write_bytes(response.content)
response=client.get("/assistant/evidence/",dict(question="근거 없는 테스트 질문",as_of="2026-10-28"))
assert response.status_code==200 and "근거 부족".encode() in response.content
(target/"ra-rendered.html").write_bytes(response.content)
print("PASS: isolated synthetic sample, 7 current / 1 previous, 2 deduplicated signals, denominator absent, no-evidence offline search.")
