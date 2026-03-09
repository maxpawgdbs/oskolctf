"""
API views — полностью совместимы с Vue SPA.
"""
import hashlib
import hmac
import json
import os

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required as dj_login_required

from ctf.models import User, Task, Solve, load_tasks_json, sync_tasks_from_json, dump_tasks_to_json


def _json_error(msg, status=400):
    return JsonResponse({"ok": False, "error": msg}, status=status)


def _require_auth(request):
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "error": "Not authenticated"}, status=401)
    return None


# ── /api/me ──────────────────────────────────────────────────────────────────────

def api_me(request):
    if request.user.is_authenticated:
        u = request.user
        return JsonResponse({
            "user": {
                "id": u.id,
                "username": u.username,
                "display_name": u.get_display_name(),
                "avatar": u.avatar.url if u.avatar else None,
                "is_staff": u.is_staff,
            }
        })
    return JsonResponse({"user": None})


# ── /api/csrf ─────────────────────────────────────────────────────────────────────

def api_csrf(request):
    from django.middleware.csrf import get_token
    return JsonResponse({"csrf": get_token(request)})


# ── /api/auth/login ───────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name="dispatch")
class ApiLogin(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except Exception:
            return _json_error("Invalid JSON")
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is None:
            return _json_error("Неверный логин или пароль")
        login(request, user)
        return JsonResponse({
            "ok": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.get_display_name(),
                "avatar": user.avatar.url if user.avatar else None,
                "is_staff": user.is_staff,
            },
        })


# ── /api/auth/register ────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name="dispatch")
class ApiRegister(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except Exception:
            return _json_error("Invalid JSON")
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        if len(username) < 3 or len(username) > 16:
            return _json_error("Username: от 3 до 16 символов")
        if len(password) < 6 or len(password) > 64:
            return _json_error("Пароль: от 6 до 64 символов")
        # Только буквы, цифры, _, -
        import re
        if not re.match(r'^[\w\-]+$', username):
            return _json_error("Username: только буквы, цифры, _ и -")
        if User.objects.filter(username__iexact=username).exists():
            return _json_error("Имя уже занято")
        user = User.objects.create_user(username=username, password=password)
        login(request, user)
        return JsonResponse({
            "ok": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.get_display_name(),
                "avatar": user.avatar.url if user.avatar else None,
                "is_staff": user.is_staff,
            },
        })


# ── /api/auth/logout ──────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name="dispatch")
class ApiLogout(View):
    def post(self, request):
        logout(request)
        return JsonResponse({"ok": True})


# ── /api/board ────────────────────────────────────────────────────────────────────

def api_board(request):
    err = _require_auth(request)
    if err:
        return err
    user = request.user

    from django.db.models import Sum, Count

    my_solves = {s.task_id: str(s.solved_at) for s in user.solves.select_related("task").all()}

    tasks_qs = Task.objects.filter(active=True).annotate(sc=Count("solves"))

    tasks = []
    for t in tasks_qs:
        tasks.append({
            "id": t.task_id,
            "name": t.name,
            "category": t.category,
            "difficulty": t.difficulty,
            "description": t.description,
            "points": t.points,
            "solved": t.id in my_solves or t.task_id in [s for s in my_solves],
            "solved_at": my_solves.get(t.id),
            "solve_count": t.sc,
            "link": t.url or f"/task{t.task_id}",
            "active": t.active,
            "has_file": bool(t.file.strip()),
            "hide_open_button": t.hide_open_button,
            "author": t.author,
            "author_url": t.author_url,
        })

    # Решения через ID модели, но сверяем по task_id
    solved_task_ids = set(
        Solve.objects.filter(user=user).values_list("task__task_id", flat=True)
    )
    for t in tasks:
        t["solved"] = t["id"] in solved_task_ids

    # Лидерборд
    lb = (
        User.objects.annotate(
            score=Sum("solves__task__points"),
            solved_count=Count("solves"),
        )
        .order_by("-score", "-solved_count", "username")[:50]
    )
    leaderboard = [
        {
            "username": u.username,
            "display_name": u.get_display_name(),
            "avatar": u.avatar.url if u.avatar else None,
            "score": u.score or 0,
            "solved_count": u.solved_count or 0,
        }
        for u in lb
    ]

    return JsonResponse({
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.get_display_name(),
            "avatar": user.avatar.url if user.avatar else None,
            "is_staff": user.is_staff,
        },
        "tasks": tasks,
        "leaderboard": leaderboard,
    })


# ── /api/submit ───────────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name="dispatch")
class ApiSubmit(View):
    def post(self, request):
        err = _require_auth(request)
        if err:
            return err
        try:
            data = json.loads(request.body)
        except Exception:
            return _json_error("Invalid JSON")
        raw_flag = (data.get("flag") or "").strip()
        if not raw_flag:
            return JsonResponse({"ok": False, "error": "Пустой флаг", "category": "error"})
        submitted_hash = hashlib.sha256(raw_flag.encode()).hexdigest()
        task = None
        for t in Task.objects.filter(active=True):
            if hmac.compare_digest(t.flag_hash(), submitted_hash):
                task = t
                break
        if task is None:
            return JsonResponse({"ok": False, "error": "Неверный флаг", "category": "error"})
        _, created = Solve.objects.get_or_create(user=request.user, task=task)
        if not created:
            return JsonResponse({
                "ok": False,
                "error": f"{task.name} уже решён",
                "category": "info",
            })
        return JsonResponse({
            "ok": True,
            "message": f"Засчитано! {task.name} (+{task.points} pts)",
            "task_id": task.task_id,
            "points": task.points,
        })


# ── /api/task-file/<task_id> ──────────────────────────────────────────────────────

def api_task_file(request, task_id: int):
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "error": "Not authenticated"}, status=401)
    try:
        task = Task.objects.get(task_id=task_id, active=True)
    except Task.DoesNotExist:
        from django.http import Http404
        raise Http404
    rel = (task.file or "").strip()
    if not rel:
        from django.http import Http404
        raise Http404
    base = os.path.realpath(settings.TASK_FILES_DIR)
    target = os.path.realpath(os.path.join(base, rel))
    if not target.startswith(base + os.sep) and target != base:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    if not os.path.isfile(target):
        from django.http import Http404
        raise Http404
    from django.http import FileResponse
    return FileResponse(open(target, "rb"), as_attachment=True, filename=os.path.basename(target))


# ── /api/profile/<username> ───────────────────────────────────────────────────────

def api_profile(request, username: str):
    err = _require_auth(request)
    if err:
        return err
    try:
        u = User.objects.get(username__iexact=username)
    except User.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Пользователь не найден"}, status=404)
    solves = u.solves.select_related("task").order_by("solved_at")
    solved_tasks = [
        {
            "task_id": s.task.task_id,
            "name": s.task.name,
            "category": s.task.category,
            "points": s.task.points,
            "solved_at": str(s.solved_at),
        }
        for s in solves
        if s.task.active
    ]
    return JsonResponse({
        "ok": True,
        "profile": {
            "id": u.id,
            "username": u.username,
            "display_name": u.get_display_name(),
            "bio": u.bio,
            "avatar": u.avatar.url if u.avatar else None,
            "score": u.get_score(),
            "solve_count": u.get_solve_count(),
            "member_since": str(u.created_at),
            "is_staff": u.is_staff,
            "solved_tasks": solved_tasks,
        },
    })


# ── /api/profile/update ───────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name="dispatch")
class ApiProfileUpdate(View):
    def post(self, request):
        err = _require_auth(request)
        if err:
            return err
        # multipart (аватар) или json
        if request.content_type and "multipart" in request.content_type:
            display_name = (request.POST.get("display_name") or "").strip()
            bio = (request.POST.get("bio") or "").strip()
            avatar_file = request.FILES.get("avatar")
        else:
            try:
                data = json.loads(request.body)
            except Exception:
                data = {}
            display_name = (data.get("display_name") or "").strip()
            bio = (data.get("bio") or "").strip()
            avatar_file = None

        user = request.user
        if len(display_name) > 32:
            return _json_error("Отображаемое имя: не больше 32 символов")
        if len(bio) > 300:
            return _json_error("О себе: не больше 300 символов")
        user.display_name = display_name
        user.bio = bio
        if avatar_file:
            # Проверка типа файла
            allowed = {"image/jpeg", "image/png", "image/gif", "image/webp"}
            if avatar_file.content_type not in allowed:
                return _json_error("Аватарка: только JPEG, PNG, GIF, WEBP")
            if avatar_file.size > 2 * 1024 * 1024:
                return _json_error("Аватарка: не больше 2 МБ")
            if user.avatar:
                # Удаляем старый файл
                try:
                    old_path = user.avatar.path
                    if os.path.isfile(old_path):
                        os.remove(old_path)
                except Exception:
                    pass
            user.avatar = avatar_file
        user.save()
        return JsonResponse({
            "ok": True,
            "display_name": user.get_display_name(),
            "avatar": user.avatar.url if user.avatar else None,
            "bio": user.bio,
        })


# ── /api/profile/change-password ─────────────────────────────────────────────────

@method_decorator(csrf_exempt, name="dispatch")
class ApiChangePassword(View):
    def post(self, request):
        err = _require_auth(request)
        if err:
            return err
        try:
            data = json.loads(request.body)
        except Exception:
            return _json_error("Invalid JSON")
        old_pw = data.get("old_password") or ""
        new_pw = data.get("new_password") or ""
        if not request.user.check_password(old_pw):
            return _json_error("Неверный текущий пароль")
        if len(new_pw) < 6 or len(new_pw) > 64:
            return _json_error("Новый пароль: от 6 до 64 символов")
        request.user.set_password(new_pw)
        request.user.save()
        # Обновляем сессию, чтобы не выкидывало
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, request.user)
        return JsonResponse({"ok": True})


# ── /api/admin/* — кастомные API для Django-независимой панели ─────────────────────

def api_admin_stats(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)
    from django.db.models import Count
    return JsonResponse({
        "ok": True,
        "users": User.objects.count(),
        "tasks": Task.objects.count(),
        "active_tasks": Task.objects.filter(active=True).count(),
        "solves": Solve.objects.count(),
    })


@method_decorator(csrf_exempt, name="dispatch")
class ApiAdminSyncTasks(View):
    """Синхронизировать tasks.json → БД."""
    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)
        # Может принять JSON-тело или синхронизировать из файла
        body = request.body
        if body:
            try:
                data = json.loads(body)
            except Exception:
                return _json_error("Invalid JSON")
            if isinstance(data, list):
                created, updated = sync_tasks_from_json(data)
            else:
                return _json_error("Ожидается массив заданий")
        else:
            # Синхронизация из файла tasks.json
            created, updated = sync_tasks_from_json()
        return JsonResponse({"ok": True, "created": created, "updated": updated})


# ── /api/announcement ────────────────────────────────────────────────────────────

def api_announcement(request):
    """Возвращает текущий баннер объявления (если есть)."""
    from django.core.cache import cache
    text = cache.get("site_announcement", "")
    return JsonResponse({"ok": True, "text": text})


# ── Новые Admin API для кастомной SPA-админки ─────────────────────────────────────

def _require_staff(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)
    return None


def api_admin_users(request):
    """GET: список пользователей."""
    err = _require_staff(request)
    if err:
        return err
    from django.db.models import Sum, Count
    users = User.objects.annotate(
        score=Sum("solves__task__points"),
        solved_count=Count("solves"),
    ).order_by("-score", "-solved_count", "username")
    return JsonResponse({"ok": True, "users": [
        {
            "id": u.id,
            "username": u.username,
            "display_name": u.get_display_name(),
            "avatar": u.avatar.url if u.avatar else None,
            "is_staff": u.is_staff,
            "is_superuser": u.is_superuser,
            "score": u.score or 0,
            "solved_count": u.solved_count or 0,
            "date_joined": str(u.date_joined)[:10],
        }
        for u in users
    ]})


@method_decorator(csrf_exempt, name="dispatch")
class api_admin_toggle_staff(View):
    def post(self, request, user_id):
        err = _require_staff(request)
        if err:
            return err
        try:
            u = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return _json_error("Пользователь не найден", 404)
        if u.is_superuser:
            return _json_error("Нельзя изменить права суперюзера")
        u.is_staff = not u.is_staff
        u.save(update_fields=["is_staff"])
        return JsonResponse({"ok": True, "is_staff": u.is_staff})


def api_admin_tasks(request):
    """GET: список всех задач."""
    err = _require_staff(request)
    if err:
        return err
    from django.db.models import Count
    tasks = Task.objects.annotate(sc=Count("solves")).order_by("task_id")
    return JsonResponse({"ok": True, "tasks": [
        {
            "id": t.task_id,
            "name": t.name,
            "category": t.category,
            "difficulty": t.difficulty,
            "points": t.points,
            "active": t.active,
            "solve_count": t.sc,
            "author": t.author,
            "author_url": t.author_url,
            "description": t.description,
            "flag": t.flag,
            "url": t.url,
            "hide_open_button": t.hide_open_button,
            "file": t.file or "",
        }
        for t in tasks
    ]})


@method_decorator(csrf_exempt, name="dispatch")
class ApiAdminTaskSave(View):
    def post(self, request, task_id):
        err = _require_staff(request)
        if err:
            return err
        try:
            task = Task.objects.get(task_id=task_id)
        except Task.DoesNotExist:
            return _json_error("Задача не найдена", 404)
        try:
            data = json.loads(request.body)
        except Exception:
            return _json_error("Invalid JSON")
        if "active" in data:
            task.active = bool(data["active"])
        if "points" in data:
            pts = int(data["points"])
            if pts < 0:
                return _json_error("Очки не могут быть отрицательными")
            task.points = pts
        # Полное редактирование (если переданы расширенные поля)
        if "name" in data:
            task.name = (data["name"] or "").strip()[:128]
        if "category" in data:
            task.category = (data["category"] or "").strip()[:32]
        if "difficulty" in data:
            task.difficulty = (data["difficulty"] or "").strip()[:32]
        if "description" in data:
            task.description = (data["description"] or "").strip()
        if "flag" in data:
            task.flag = (data["flag"] or "").strip()[:256]
        if "url" in data:
            task.url = (data["url"] or "").strip()[:128]
        if "hide_open_button" in data:
            task.hide_open_button = bool(data["hide_open_button"])
        if "author" in data:
            task.author = (data["author"] or "").strip()[:64]
        if "author_url" in data:
            task.author_url = (data["author_url"] or "").strip()[:200]
        task.save()
        dump_tasks_to_json()
        return JsonResponse({"ok": True})


@method_decorator(csrf_exempt, name="dispatch")
class ApiAdminTaskCreate(View):
    def post(self, request):
        err = _require_staff(request)
        if err:
            return err
        try:
            data = json.loads(request.body)
        except Exception:
            return _json_error("Invalid JSON")
        # Обязательные поля
        name = (data.get("name") or "").strip()
        flag = (data.get("flag") or "").strip()
        if not name:
            return _json_error("Название обязательно")
        if not flag:
            return _json_error("Флаг обязателен")
        # task_id: если не передан — берём max + 1
        task_id = data.get("task_id")
        if task_id is not None:
            try:
                task_id = int(task_id)
            except (ValueError, TypeError):
                return _json_error("task_id должен быть числом")
            if Task.objects.filter(task_id=task_id).exists():
                return _json_error(f"Задание с ID {task_id} уже существует")
        else:
            max_id = Task.objects.order_by("-task_id").values_list("task_id", flat=True).first()
            task_id = (max_id or 0) + 1
        task = Task(
            task_id=task_id,
            name=name[:128],
            category=(data.get("category") or "Разное").strip()[:32],
            difficulty=(data.get("difficulty") or "Среднее").strip()[:32],
            description=(data.get("description") or "").strip(),
            points=max(0, int(data.get("points") or 100)),
            flag=flag[:256],
            url=(data.get("url") or "").strip()[:128],
            active=bool(data.get("active", True)),
            hide_open_button=bool(data.get("hide_open_button", False)),
            author=(data.get("author") or "").strip()[:64],
            author_url=(data.get("author_url") or "").strip()[:200],
        )
        task.save()
        dump_tasks_to_json()
        return JsonResponse({"ok": True, "task_id": task.task_id, "name": task.name})


@csrf_exempt
def api_admin_task_delete(request, task_id):
    err = _require_staff(request)
    if err:
        return err
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST only"}, status=405)
    try:
        task = Task.objects.get(task_id=task_id)
    except Task.DoesNotExist:
        return _json_error("Задача не найдена", 404)
    task.delete()
    dump_tasks_to_json()
    return JsonResponse({"ok": True})


@csrf_exempt
def api_admin_task_clear_solves(request, task_id):
    err = _require_staff(request)
    if err:
        return err
    n = Solve.objects.filter(task__task_id=task_id).delete()[0]
    return JsonResponse({"ok": True, "deleted": n})


@csrf_exempt
def api_admin_reset_solves(request):
    err = _require_staff(request)
    if err:
        return err
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST only"}, status=405)
    n = Solve.objects.all().delete()[0]
    return JsonResponse({"ok": True, "deleted": n})


@method_decorator(csrf_exempt, name="dispatch")
class ApiAdminSetAnnouncement(View):
    def post(self, request):
        err = _require_staff(request)
        if err:
            return err
        try:
            data = json.loads(request.body)
        except Exception:
            return _json_error("Invalid JSON")
        from django.core.cache import cache
        text = (data.get("text") or "").strip()[:500]
        if text:
            cache.set("site_announcement", text, timeout=None)
        else:
            cache.delete("site_announcement")
        return JsonResponse({"ok": True, "text": text})


_CATEGORY_FOLDER = {
    'Web': 'web',
    'Разное': 'misc',
    'Крипто': 'crypto',
    'Форензика': 'forenzika',
    'Реверс': 'revers',
    'Pwn': 'pwn',
    'ОСИНТ': 'osint',
}


@method_decorator(csrf_exempt, name="dispatch")
class ApiAdminTaskUploadFile(View):
    MAX_SIZE = 64 * 1024 * 1024  # 64 МБ

    def post(self, request, task_id):
        import re
        from pathlib import Path

        err = _require_staff(request)
        if err:
            return err
        try:
            task = Task.objects.get(task_id=task_id)
        except Task.DoesNotExist:
            return _json_error("Задача не найдена", 404)

        f = request.FILES.get("file")
        if not f:
            return _json_error("Файл не передан")

        # Безопасное имя файла — только буквы, цифры, дефис, точка, подчёркивание
        # os.path.basename не обрезает Windows-пути на Linux,
        # поэтому нормализуем оба разделителя вручную
        filename = f.name.replace('\\', '/').split('/')[-1]
        if not re.match(r'^[\w\-. ]+$', filename):
            return _json_error("Недопустимое имя файла (разрешены: буквы, цифры, -, _, пробел, .)")
        if f.size > ApiAdminTaskUploadFile.MAX_SIZE:
            return _json_error("Файл не должен превышать 64 МБ")

        subdir = _CATEGORY_FOLDER.get(task.category, 'misc')
        task_dir = Path(settings.BASE_DIR) / 'task' / subdir
        task_dir.mkdir(parents=True, exist_ok=True)

        dest = task_dir / filename
        with open(dest, 'wb') as out:
            for chunk in f.chunks():
                out.write(chunk)

        # Сохраняем путь в базу, чтобы борд показал кнопку скачать
        task.file = f"{subdir}/{filename}"
        task.save(update_fields=['file'])
        dump_tasks_to_json()

        return JsonResponse({"ok": True, "filename": filename, "path": f"/task/{subdir}/{filename}"})
