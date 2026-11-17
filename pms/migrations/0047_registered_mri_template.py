import json
from pathlib import Path
from django.db import migrations


def seed(apps,schema_editor):
    Template=apps.get_model("pms","WritingTemplate")
    template=next(t for t in json.loads(Path(__file__).with_name("data").joinpath("mri_catalog_v1.json").read_text(encoding="utf-8"))["templates"] if t["key"]=="mri-equipment")
    template.update(version=2,checked_on="2026-11-16")
    template["conditions"]["internal_collection"]=True
    template["conditions"]["include"]="Registered MRI model/configuration; internal draft before RA classification and pathway confirmation"
    template["fields"].update(target_population="Target population",magnet_type="Magnet type",accessories="Components and accessories")
    extra=[("MRI.PRED","Predicate Device Comparison","IV.A. Indications for Use",7,"Predicates and Substantial Equivalence"),
           ("MRI.EMC","Electrical safety and EMC","V. System Safety",11,"Electrical Safety and Electromagnetic Compatibility"),
           ("MRI.SW","MRI system software documentation","IV.B. Device Description",8,"Software"),
           ("MRI.RISK","Risk management and system safety","V. System Safety",11,"Risk Management")]
    for id,title,clause,page,mapping in extra:
        template["items"].append(dict(id=id,title=title,condition="always",evidence_type="Product specification / verified report",
            source_key="mrdd",source_section=clause,page=page,draft_section=title,mapping=mapping,
            test_required=id=="MRI.EMC"))
    for row in template["items"]:
        if row["id"] in ("MRI.USE","MRI.SPEC","MRI.COIL"):row["mapping"]="Device Description"
        elif row["id"]=="MRI.LABEL":row["mapping"]="Labeling"
        elif row["id"] not in {x[0] for x in extra}:row["mapping"]="Performance Testing"
    Template.objects.get_or_create(key="mri-equipment",version=2,defaults={k:v for k,v in template.items() if k not in ("key","version")})


class Migration(migrations.Migration):
    dependencies=[("pms","0046_mri_registration")]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop)]
