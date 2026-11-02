from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('pms', '0011_merge_workflow_branches')]

    # Historical completed tasks have no reliable completion timestamp. Preserve
    # NULL instead of inventing one; the UI labels that legacy state explicitly.
    operations = [
        migrations.AddField(
            model_name='worktask', name='completed_at',
            field=models.DateTimeField('완료일', null=True, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name='recoveryentry', name='submission_key',
            field=models.UUIDField(null=True, blank=True, unique=True, editable=False),
        ),
    ]
