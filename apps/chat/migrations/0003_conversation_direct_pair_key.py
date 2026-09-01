# Generated migration to add direct_pair_key field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0002_conversationrating'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='direct_pair_key',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Deterministic unique key for 1-on-1 conversations: min_id_max_id',
                max_length=120,
                null=True,
            ),
        ),
    ]
