import django.db.models.deletion
import uuid
import secrets
import string
from django.conf import settings
from django.db import migrations, models

def populate_invite_codes(apps, schema_editor):
    Profile = apps.get_model('accounts', 'Profile')
    chars = string.ascii_uppercase + string.digits
    used_codes = set()
    for p in Profile.objects.all():
        code = ''.join(secrets.choice(chars) for _ in range(8))
        while code in used_codes:
            code = ''.join(secrets.choice(chars) for _ in range(8))
        used_codes.add(code)
        p.invite_code = code
        p.save(update_fields=['invite_code'])

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_interest_profile_interests'),
    ]

    operations = [
        migrations.CreateModel(
            name='Referral',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('invite_code', models.CharField(db_index=True, max_length=20)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('qualified', 'Qualified'), ('invalidated', 'Invalidated')], db_index=True, default='pending', max_length=15)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('qualified_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Referral',
                'verbose_name_plural': 'Referrals',
            },
        ),
        migrations.AddField(
            model_name='profile',
            name='badge',
            field=models.CharField(choices=[('new_member', 'New Member'), ('active_member', 'Active Member'), ('connector', 'Connector'), ('trusted_member', 'Trusted Member')], db_index=True, default='new_member', max_length=20, verbose_name='Community Badge'),
        ),
        migrations.AddField(
            model_name='profile',
            name='invite_code',
            field=models.CharField(blank=True, db_index=True, default='', max_length=12, verbose_name='Invite Code'),
        ),
        migrations.RunPython(populate_invite_codes, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name='profile',
            index=models.Index(fields=['invite_code'], name='accounts_pr_invite__b83070_idx'),
        ),
        migrations.AddIndex(
            model_name='profile',
            index=models.Index(fields=['badge'], name='accounts_pr_badge_c1f653_idx'),
        ),
        migrations.AddField(
            model_name='referral',
            name='inviter',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sent_referrals', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='referral',
            name='referred_user',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='received_referral', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddIndex(
            model_name='referral',
            index=models.Index(fields=['inviter', 'status'], name='accounts_re_inviter_7c3fbf_idx'),
        ),
        migrations.AddIndex(
            model_name='referral',
            index=models.Index(fields=['created_at'], name='accounts_re_created_f889b0_idx'),
        ),
    ]
