from django.db import migrations


def seed(apps, schema_editor):
    Template = apps.get_model("pms", "WritingTemplate")
    for key, number in (("eu-mdr", "745"), ("eu-ivdr", "746")):
        celex = "32017R0" + number
        rows = [
            ("EU.II.1", "Device description and specification", "Annex II, section 1"),
            ("EU.II.2", "Information supplied by the manufacturer", "Annex II, section 2"),
            ("EU.II.3", "Design and manufacturing information", "Annex II, section 3"),
            ("EU.II.4", "General safety and performance requirements", "Annex II, section 4; Annex I"),
            ("EU.II.5", "Benefit-risk analysis and risk management", "Annex II, section 5"),
            ("EU.II.6", "Product verification and validation", "Annex II, section 6"),
            ("EU.III", "Post-market surveillance documentation", "Annex III"),
        ]
        Template.objects.get_or_create(key=key, version=1, defaults={
            "name": "EU " + ("MDR" if number == "745" else "IVDR") + " Technical Documentation",
            "market": "EU", "pathway": "RA conformity assessment review", "state": "PUBLISHED",
            "example": False, "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:" + celex,
            "issued_on": "2017-04-05", "checked_on": "2026-11-15",
            "conditions": {"scope": "eu", "regulations": ["2017/" + number, "MDR" if number == "745" else "IVDR"],
                           "include": "RA must select the applicable act version and provisions",
                           "exclude": "Classification and conformity assessment route require separate RA review"},
            "fields": {"contacts": "Patient contact", "reprocessing": "Reuse / reprocessing",
                       "software": "Software version / not applicable", "wireless": "Wireless / not applicable"},
            "items": [{"id": item, "title": title, "condition": "always", "evidence_type": "Product documentation",
                       "source_section": clause, "page": 0, "draft_section": title, "mapping": title}
                      for item, title, clause in rows],
        })
    Template.objects.get_or_create(key="eu-common", version=1, defaults={
        "name": "EU common evidence collection", "market": "EU", "pathway": "RA verification required",
        "state": "PUBLISHED", "checked_on": "2026-11-15", "fields": {}, "source_url": "",
        "conditions": {"scope": "collection", "include": "Unconfirmed regulatory framework", "exclude": "Device-specific drafting pending RA review"},
        "items": [{"id": "EU.COMMON", "title": "Device information and evidence collection", "condition": "always",
                   "evidence_type": "Product records", "source_section": "RA selection required", "page": 0,
                   "draft_section": "Device information", "mapping": "RA verification required"}],
    })


class Migration(migrations.Migration):
    dependencies = [("pms", "0042_eu_legal_evidence")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
