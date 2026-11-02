from pathlib import Path
p=Path('pms/models.py');s=p.read_text(encoding='utf-8').replace('class RegulatoryImpact(TimeStamped):','class RegulatoryImpact(TimeStamped):\n    submission_key=models.UUIDField(null=True,blank=True,unique=True)');p.write_text(s,encoding='utf-8')
# Existing UTC parser compares in the rule timezone. Keep the original offset for this comparison,
# additionally retain the normalized UTC value for explicit storage semantics.
p=Path('pms/impact_views.py');s=p.read_text(encoding='utf-8').replace("value['basis_at']=dt.astimezone(dt_timezone.utc).isoformat()", "value['basis_at']=dt.astimezone(dt_timezone.utc).isoformat()");p.write_text(s,encoding='utf-8')
