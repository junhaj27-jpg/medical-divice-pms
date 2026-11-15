import hashlib
import json
from pathlib import Path
from django.db import migrations


def seed(apps, schema_editor):
    data = json.loads(Path(__file__).with_name("data").joinpath("mri_catalog_v1.json").read_text(encoding="utf-8"))
    Source = apps.get_model("pms", "FDAReferenceVersion")
    Template = apps.get_model("pms", "WritingTemplate")
    for source in data["sources"]:
        identity = {k: str(v) if k in ("issued_on", "revised_on") else v for k, v in source.items() if k not in ("key", "checked_on")}
        fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        Source.objects.get_or_create(key=source["key"], version=1, defaults={**{k:v for k,v in source.items() if k != "key"}, "content_hash":fingerprint})
    for template in data["templates"]:
        Template.objects.get_or_create(key=template["key"],version=1,defaults={k:v for k,v in template.items() if k not in ("key","version")})


class Migration(migrations.Migration):
    dependencies = [("pms", "0044_fda_library")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
