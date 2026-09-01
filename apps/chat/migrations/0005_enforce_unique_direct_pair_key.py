# Generated migration to enforce unique constraint on direct_pair_key

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0004_merge_duplicates_and_populate_keys'),
    ]

    operations = [
        migrations.AlterField(
            model_name='conversation',
            name='direct_pair_key',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Deterministic unique key for 1-on-1 conversations: min_id_max_id',
                max_length=120,
                null=True,
                unique=True,
            ),
        ),
    ]
