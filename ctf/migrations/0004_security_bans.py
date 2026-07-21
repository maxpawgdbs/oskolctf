import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ctf", "0003_audit_log")]

    operations = [
        migrations.CreateModel(
            name="ClientTrace",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ip", models.GenericIPAddressField(blank=True, db_index=True, null=True)),
                ("signature_hash", models.CharField(blank=True, db_index=True, max_length=64)),
                ("user_agent_hash", models.CharField(blank=True, db_index=True, max_length=64)),
                ("first_seen", models.DateTimeField(default=django.utils.timezone.now)),
                ("last_seen", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("seen_count", models.PositiveIntegerField(default=1)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="client_traces", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-last_seen"]},
        ),
        migrations.CreateModel(
            name="SecurityBan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("account", "Account"), ("ip", "IP / CIDR"), ("signature", "Client signature"), ("user_agent", "User-Agent hash")], db_index=True, max_length=16)),
                ("value", models.CharField(blank=True, db_index=True, max_length=128)),
                ("reason", models.CharField(blank=True, max_length=300)),
                ("active", models.BooleanField(db_index=True, default=True)),
                ("expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_security_bans", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="security_bans", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="clienttrace",
            constraint=models.UniqueConstraint(fields=("user", "ip", "signature_hash", "user_agent_hash"), name="unique_user_client_trace"),
        ),
        migrations.AddConstraint(
            model_name="securityban",
            constraint=models.UniqueConstraint(condition=models.Q(("active", True)), fields=("kind", "user", "value"), name="unique_active_security_ban"),
        ),
    ]
