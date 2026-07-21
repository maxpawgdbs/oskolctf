from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ctf', '0001_initial'),
    ]

    operations = [
        # Поле points_awarded в Solve
        migrations.AddField(
            model_name='solve',
            name='points_awarded',
            field=models.PositiveIntegerField(default=0, verbose_name='Очков получено'),
        ),
        # Таблица DynamicPricingConfig
        migrations.CreateModel(
            name='DynamicPricingConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enabled', models.BooleanField(default=False, verbose_name='Включить динамические цены',
                    help_text='Если включено — стоимость задания уменьшается с каждым новым решением.')),
                ('decay_per_solve', models.PositiveIntegerField(default=5, verbose_name='Снижение за каждое решение (очки)',
                    help_text='На сколько очков снижается цена задания за каждое новое решение.')),
                ('min_percent', models.PositiveIntegerField(default=20, verbose_name='Минимальная цена (% от базовой)',
                    help_text='Минимальная цена задания в процентах от базовой стоимости (1–100). Например, 20 = не ниже 20% от базы.')),
            ],
            options={
                'verbose_name': 'Настройки динамических цен',
                'verbose_name_plural': 'Настройки динамических цен',
            },
        ),
    ]
