import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ctf', '0002_dynamic_pricing'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Время')),
                ('action', models.CharField(
                    choices=[
                        ('register',          'Регистрация'),
                        ('login',             'Вход'),
                        ('logout',            'Выход'),
                        ('submit_correct',    'Флаг принят'),
                        ('submit_wrong',      'Неверный флаг'),
                        ('task_create',       'Создание задания'),
                        ('task_edit',         'Редактирование задания'),
                        ('task_delete',       'Удаление задания'),
                        ('grant_staff',       'Выдача прав admin'),
                        ('revoke_staff',      'Отзыв прав admin'),
                        ('reset_all_solves',  'Сброс всех решений'),
                        ('clear_task_solves', 'Сброс решений задания'),
                    ],
                    max_length=64,
                    verbose_name='Действие',
                )),
                ('details', models.JSONField(blank=True, default=dict, verbose_name='Детали')),
                ('ip', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP')),
                ('actor', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='audit_logs',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Автор действия',
                )),
                ('target_task', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='audit_logs',
                    to='ctf.task',
                    verbose_name='Целевое задание',
                )),
                ('target_user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='target_audit_logs',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Целевой пользователь',
                )),
            ],
            options={
                'verbose_name': 'Запись журнала',
                'verbose_name_plural': 'Журнал действий',
                'ordering': ['-timestamp'],
            },
        ),
    ]
