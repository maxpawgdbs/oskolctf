"""
Кастомная Django-админка для OSKOLCTF.
"""
import json

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjUserAdmin
from django.contrib.admin import AdminSite
from django.http import HttpResponseRedirect
from django.urls import path
from django.utils.html import format_html
from django.shortcuts import render
from django import forms

from ctf.models import User, Task, Solve, DynamicPricingConfig, AuditLog, load_tasks_json, sync_tasks_from_json


# ── Кастомный AdminSite ───────────────────────────────────────────────────────────

class OskolCTFAdminSite(AdminSite):
    site_header = "OSKOLCTF Admin"
    site_title = "OSKOLCTF"
    index_title = "Панель управления"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("sync-tasks/", self.admin_view(self.sync_tasks_view), name="sync_tasks"),
            path("import-json/", self.admin_view(self.import_json_view), name="import_json"),
            path("reset-solves/", self.admin_view(self.reset_solves_view), name="reset_solves"),
            path("top-users/", self.admin_view(self.top_users_view), name="top_users"),
            path("announcements/", self.admin_view(self.announcements_view), name="announcements"),
            path("dynamic-pricing/", self.admin_view(self.dynamic_pricing_view), name="dynamic_pricing"),
        ]
        return custom + urls

    def sync_tasks_view(self, request):
        """Синхронизация tasks.json → БД одним кликом."""
        created, updated = sync_tasks_from_json()
        self.message_user(request, f"Синхронизация выполнена: создано {created}, обновлено {updated}")
        return HttpResponseRedirect("../")

    def import_json_view(self, request):
        """Импорт задач из загружаемого JSON-файла или вставленного текста."""
        ctx = self.each_context(request)
        ctx["title"] = "Импорт задач из JSON"
        ctx["error"] = None
        ctx["success"] = None

        if request.method == "POST":
            json_text = request.POST.get("json_text", "").strip()
            json_file = request.FILES.get("json_file")
            raw = None
            if json_file:
                raw = json_file.read().decode("utf-8")
            elif json_text:
                raw = json_text
            if raw:
                try:
                    data = json.loads(raw)
                    if not isinstance(data, list):
                        ctx["error"] = "Ожидается массив JSON"
                    else:
                        created, updated = sync_tasks_from_json(data)
                        ctx["success"] = f"Импортировано: создано {created}, обновлено {updated}"
                except Exception as e:
                    ctx["error"] = f"Ошибка парсинга JSON: {e}"
            else:
                ctx["error"] = "Нет данных для импорта"

        return render(request, "admin/import_json.html", ctx)

    def reset_solves_view(self, request):
        """Сброс всех решений (ядерная кнопка)."""
        ctx = self.each_context(request)
        ctx["title"] = "Сброс решений"
        if request.method == "POST" and request.POST.get("confirm") == "yes":
            count = Solve.objects.count()
            Solve.objects.all().delete()
            self.message_user(request, f"Удалено {count} решений")
            return HttpResponseRedirect("../")
        ctx["solve_count"] = Solve.objects.count()
        return render(request, "admin/reset_solves.html", ctx)

    def top_users_view(self, request):
        """Топ участников прямо в админке."""
        from django.db.models import Sum, Count
        ctx = self.each_context(request)
        ctx["title"] = "Топ участников"
        ctx["users"] = (
            User.objects.annotate(
                score=Sum("solves__task__points"),
                solved_count=Count("solves"),
            )
            .order_by("-score", "-solved_count", "username")[:100]
        )
        return render(request, "admin/top_users.html", ctx)

    def announcements_view(self, request):
        """Страница для анонсов (сохраняется в сессии, отображается на SPA)."""
        ctx = self.each_context(request)
        ctx["title"] = "Анонс / баннер"
        if request.method == "POST":
            text = request.POST.get("text", "").strip()[:500]
            from django.core.cache import cache
            cache.set("site_announcement", text, timeout=None)
            self.message_user(request, "Анонс обновлён!")
        from django.core.cache import cache
        ctx["current"] = cache.get("site_announcement", "")
        return render(request, "admin/announcements.html", ctx)

    def dynamic_pricing_view(self, request):
        """Заставка настроек динамического ценообразования."""
        ctx = self.each_context(request)
        ctx["title"] = "Динамические цены"
        cfg = DynamicPricingConfig.get_config()
        ctx["cfg"] = cfg
        ctx["error"] = None
        ctx["success"] = None
        if request.method == "POST":
            try:
                cfg.enabled = request.POST.get("enabled") == "on"
                decay = int(request.POST.get("decay_per_solve", 5))
                min_pct = int(request.POST.get("min_percent", 20))
                if decay < 0:
                    raise ValueError("Снижение не может быть отрицательным")
                if not (1 <= min_pct <= 100):
                    raise ValueError("Минимальный % должен быть от 1 до 100")
                cfg.decay_per_solve = decay
                cfg.min_percent = min_pct
                cfg.save()
                ctx["success"] = "Настройки сохранены"
            except (ValueError, TypeError) as e:
                ctx["error"] = str(e)
        # Превью: текущие цены заданий
        from django.db.models import Count
        ctx["tasks_preview"] = [
            {
                "name": t.name,
                "base": t.points,
                "current": t.get_current_points(),
                "solves": t.solve_count,
            }
            for t in Task.objects.filter(active=True).annotate(sc=Count("solves"))[:20]
        ]
        return render(request, "admin/dynamic_pricing.html", ctx)


ctf_admin_site = OskolCTFAdminSite(name="ctfadmin")


# ── Регистрация моделей ───────────────────────────────────────────────────────────

class UserAdminForm(forms.ModelForm):
    class Meta:
        model = User
        fields = "__all__"


@admin.register(User, site=ctf_admin_site)
class UserAdmin(DjUserAdmin):
    list_display = ("username", "display_name", "is_staff", "is_superuser", "get_score_display", "created_at")
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("username", "display_name")
    readonly_fields = ("created_at", "get_score_display")
    fieldsets = DjUserAdmin.fieldsets + (
        ("Профиль CTF", {"fields": ("display_name", "avatar", "bio", "created_at")}),
    )
    actions = ["make_staff", "remove_staff", "reset_user_solves"]

    @admin.display(description="Очки")
    def get_score_display(self, obj):
        return obj.get_score()

    @admin.action(description="Выдать права администратора")
    def make_staff(self, request, queryset):
        queryset.update(is_staff=True)
        self.message_user(request, f"Выдано прав: {queryset.count()}")

    @admin.action(description="Забрать права администратора")
    def remove_staff(self, request, queryset):
        queryset.update(is_staff=False)
        self.message_user(request, f"Права забраны: {queryset.count()}")

    @admin.action(description="Сбросить решения выбранных пользователей")
    def reset_user_solves(self, request, queryset):
        for user in queryset:
            user.solves.all().delete()
        self.message_user(request, "Решения сброшены")


class TaskAdminForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = "__all__"
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }


@admin.register(Task, site=ctf_admin_site)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("task_id", "name", "category", "difficulty", "points", "active", "solve_count_display", "author")
    list_filter = ("category", "difficulty", "active")
    search_fields = ("name", "description", "flag")
    list_editable = ("active", "points")
    ordering = ("task_id",)
    readonly_fields = ("solve_count_display", "created_at")
    actions = ["activate_tasks", "deactivate_tasks", "clear_task_solves"]

    @admin.display(description="Решений")
    def solve_count_display(self, obj):
        return obj.solve_count

    @admin.action(description="Активировать задания")
    def activate_tasks(self, request, queryset):
        queryset.update(active=True)

    @admin.action(description="Деактивировать задания")
    def deactivate_tasks(self, request, queryset):
        queryset.update(active=False)

    @admin.action(description="Удалить решения для выбранных заданий")
    def clear_task_solves(self, request, queryset):
        for task in queryset:
            task.solves.all().delete()
        self.message_user(request, "Решения удалены")


@admin.register(Solve, site=ctf_admin_site)
class SolveAdmin(admin.ModelAdmin):
    list_display = ("user", "task", "solved_at")
    list_filter = ("task__category",)
    search_fields = ("user__username", "task__name")
    date_hierarchy = "solved_at"


@admin.register(AuditLog, site=ctf_admin_site)
class AuditLogAdmin(admin.ModelAdmin):
    list_display    = ("timestamp", "actor", "action", "target_user", "target_task", "ip")
    list_filter     = ("action",)
    search_fields   = ("actor__username", "target_user__username", "target_task__name", "ip")
    readonly_fields = ("timestamp", "actor", "action", "target_user", "target_task", "details", "ip")
    date_hierarchy  = "timestamp"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ── Подключаем ctf_admin_site к стандартному admin (чтобы /admin/ работал) ────────

# Дублируем регистрацию в дефолтном admin для удобства
try:
    admin.site.register(User, UserAdmin)
    admin.site.register(Task, TaskAdmin)
    admin.site.register(Solve, SolveAdmin)
except admin.sites.AlreadyRegistered:
    pass
