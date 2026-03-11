import hashlib
import json
import os

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


# ─── Пользователь ───────────────────────────────────────────────────────────────

class User(AbstractUser):
    """Расширенная модель пользователя."""

    display_name = models.CharField(
        max_length=32,
        blank=True,
        verbose_name="Отображаемое имя",
        help_text="Публичное имя (если не задано — используется username)",
    )
    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
        verbose_name="Аватарка",
    )
    bio = models.TextField(
        blank=True,
        max_length=300,
        verbose_name="О себе",
    )
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Зарегистрирован")

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def get_display_name(self):
        return self.display_name or self.username

    def get_score(self):
        from django.db.models import Sum
        total = self.solves.filter(task__active=True).aggregate(
            s=Sum("points_awarded")
        )["s"]
        return total or 0

    def get_solve_count(self):
        return self.solves.filter(task__active=True).count()


# ─── Задание ────────────────────────────────────────────────────────────────────

CATEGORY_CHOICES = [
    ("Web", "Web"),
    ("Разное", "Разное"),
    ("Крипто", "Крипто"),
    ("Форензика", "Форензика"),
    ("Реверс", "Реверс"),
    ("Pwn", "Pwn"),
    ("ОСИНТ", "ОСИНТ"),
]

DIFFICULTY_CHOICES = [
    ("Очень лёгкое", "Очень лёгкое"),
    ("Лёгкое", "Лёгкое"),
    ("Среднее", "Среднее"),
    ("Сложное", "Сложное"),
    ("Очень сложное", "Очень сложное"),
]


class Task(models.Model):
    """Задание CTF."""

    task_id = models.IntegerField(unique=True, verbose_name="ID задания")
    name = models.CharField(max_length=128, verbose_name="Название")
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, verbose_name="Категория")
    difficulty = models.CharField(max_length=32, choices=DIFFICULTY_CHOICES, verbose_name="Сложность")
    description = models.TextField(blank=True, verbose_name="Описание")
    points = models.PositiveIntegerField(default=100, verbose_name="Очки")
    flag = models.CharField(max_length=256, verbose_name="Флаг")
    url = models.CharField(max_length=128, blank=True, verbose_name="URL страницы")
    active = models.BooleanField(default=True, verbose_name="Активно")
    hide_open_button = models.BooleanField(default=False, verbose_name="Скрыть кнопку 'Открыть'")
    file = models.CharField(max_length=256, blank=True, verbose_name="Файл задания (rel. path)")
    author = models.CharField(max_length=64, blank=True, verbose_name="Автор")
    author_url = models.URLField(blank=True, verbose_name="Ссылка на автора")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Создано")

    class Meta:
        verbose_name = "Задание"
        verbose_name_plural = "Задания"
        ordering = ["task_id"]

    def __str__(self):
        return f"[{self.task_id}] {self.name}"

    def flag_hash(self) -> str:
        return hashlib.sha256(self.flag.strip().encode()).hexdigest()

    @property
    def solve_count(self):
        return self.solves.count()

    def get_current_points(self):
        """Возвращает текущую стоимость с учётом динамического ценообразования."""
        try:
            cfg = DynamicPricingConfig.get_config()
            if not cfg.enabled:
                return self.points
            solves = self.solve_count
            min_pts = max(1, self.points * cfg.min_percent // 100)
            decayed = self.points - cfg.decay_per_solve * solves
            return max(min_pts, decayed)
        except Exception:
            return self.points


# ─── Решение ────────────────────────────────────────────────────────────────────

class Solve(models.Model):
    """Факт решения задания пользователем."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="solves")
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="solves")
    solved_at = models.DateTimeField(default=timezone.now, verbose_name="Время решения")
    points_awarded = models.PositiveIntegerField(default=0, verbose_name="Очков получено")

    class Meta:
        unique_together = ("user", "task")
        verbose_name = "Решение"
        verbose_name_plural = "Решения"
        ordering = ["solved_at"]

    def __str__(self):
        return f"{self.user.username} → {self.task.name}"


# ─── Динамическое ценообразование ───────────────────────────────────────────────

class DynamicPricingConfig(models.Model):
    """Синглтон-конфиг для динамического ценообразования заданий."""

    enabled = models.BooleanField(
        default=False,
        verbose_name="Включить динамические цены",
        help_text="Если включено — стоимость задания уменьшается с каждым новым решением.",
    )
    decay_per_solve = models.PositiveIntegerField(
        default=5,
        verbose_name="Снижение за каждое решение (очки)",
        help_text="На сколько очков снижается цена задания за каждое новое решение.",
    )
    min_percent = models.PositiveIntegerField(
        default=20,
        verbose_name="Минимальная цена (% от базовой)",
        help_text="Минимальная цена задания в процентах от базовой стоимости (1–100). Например, 20 = не ниже 20% от базы.",
    )

    class Meta:
        verbose_name = "Настройки динамических цен"
        verbose_name_plural = "Настройки динамических цен"

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# ─── Вспомогательные функции для tasks.json ────────────────────────────────────

def load_tasks_json() -> list:
    path = getattr(settings, "TASKS_FILE", "tasks.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def dump_tasks_to_json() -> None:
    """Сохраняет все задания из БД обратно в tasks.json."""
    path = getattr(settings, "TASKS_FILE", "tasks.json")
    tasks = Task.objects.all().order_by("task_id")
    data = [
        {
            "id": t.task_id,
            "name": t.name,
            "category": t.category,
            "difficulty": t.difficulty,
            "description": t.description,
            "points": t.points,
            "flag": t.flag,
            "url": t.url,
            "active": t.active,
            "hide_open_button": t.hide_open_button,
            "author": t.author,
            "author_url": t.author_url,
        }
        for t in tasks
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def sync_tasks_from_json(data: list | None = None) -> tuple[int, int]:
    """Синхронизирует базу данных с tasks.json.
    Возвращает (created, updated) счётчики.
    """
    if data is None:
        data = load_tasks_json()
    created = updated = 0
    for item in data:
        tid = int(item["id"])
        defaults = {
            "name": item.get("name", ""),
            "category": item.get("category", "Разное"),
            "difficulty": item.get("difficulty", "Лёгкое"),
            "description": item.get("description", ""),
            "points": int(item.get("points", 100)),
            "flag": item.get("flag", ""),
            "url": item.get("url", f"/task{tid}"),
            "active": bool(item.get("active", True)),
            "hide_open_button": bool(item.get("hide_open_button", False)),
            "file": item.get("file", ""),
            "author": item.get("author", ""),
            "author_url": item.get("author_url", ""),
        }
        obj, was_created = Task.objects.update_or_create(task_id=tid, defaults=defaults)
        if was_created:
            created += 1
        else:
            updated += 1
    return created, updated
