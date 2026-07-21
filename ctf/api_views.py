"""
API views — полностью совместимы с Vue SPA.
"""
import hashlib
import hmac
import json
import os
from io import BytesIO
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views import View

from ctf.models import SecurityBan, User, Task, Solve, DynamicPricingConfig, AuditLog, log_action, load_tasks_json, sync_tasks_from_json, dump_tasks_to_json
from ctf.security import BAN_KIND_LABELS, find_matching_ban, get_client_ip, public_ban_payload, record_client_trace, revoke_user_sessions


def _json_error(msg, status=400):
    return JsonResponse({"ok": False, "error": msg}, status=status)


def _require_auth(request):
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "error": "Not authenticated"}, status=401)
    return None


def _require_superuser(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return JsonResponse({"ok": False, "error": "Superuser access required"}, status=403)
    return None


def _parse_json(request):
    try:
        value = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _password_error(password, user=None):
    if len(password) > 128:
        return "Password is too long"
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        return " ".join(exc.messages)
    return None


def _sanitize_avatar(uploaded):
    """Decode and re-encode images so MIME spoofing and image polyglots are not stored."""
    if uploaded.size > 2 * 1024 * 1024:
        raise ValidationError("Аватар: не больше 2 МБ")
    from PIL import Image, ImageOps, UnidentifiedImageError

    raw = uploaded.read()
    try:
        image = Image.open(BytesIO(raw))
        image.verify()
        image = Image.open(BytesIO(raw))
        if image.width * image.height > 16_000_000:
            raise ValidationError("Аватар: слишком большое разрешение")
        image = ImageOps.exif_transpose(image)
        image.thumbnail((1024, 1024))
        output = BytesIO()
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            image.convert("RGBA").save(output, format="PNG", optimize=True)
            extension = "png"
        else:
            image.convert("RGB").save(output, format="JPEG", quality=88, optimize=True)
            extension = "jpg"
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("Аватар: повреждённый или неподдерживаемый файл") from exc
    from django.utils.crypto import get_random_string

    return ContentFile(output.getvalue(), name=f"avatar-{get_random_string(20)}.{extension}")


def _rate_cache_key(value):
    return "security-rate:" + hashlib.sha256(value.encode()).hexdigest()


def _rate_limited(key, limit, seconds, increment=False):
    cache_key = _rate_cache_key(key)
    count = cache.get(cache_key, 0)
    if increment:
        if count:
            try:
                cache.incr(cache_key)
            except ValueError:
                cache.set(cache_key, count + 1, seconds)
        else:
            cache.set(cache_key, 1, seconds)
    return count >= limit


def _sync_tasks_file_safe():
    """Всегда подтягивает актуальные задания из task(s).json в БД."""
    try:
        sync_tasks_from_json()
    except Exception:
        # Не валим API из-за проблем чтения JSON.
        pass


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
                "is_superuser": u.is_superuser,
            }
        })
    return JsonResponse({"user": None})


# ── /api/csrf ─────────────────────────────────────────────────────────────────────

def api_csrf(request):
    from django.middleware.csrf import get_token
    return JsonResponse({"csrf": get_token(request)})


# ── /api/auth/login ───────────────────────────────────────────────────────────────

class ApiLogin(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except Exception:
            return _json_error("Invalid JSON")
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        rate_key = f"login:{get_client_ip(request)}:{username.casefold()}"
        if _rate_limited(rate_key, 10, 300):
            return _json_error("Слишком много попыток входа. Попробуйте позже.", 429)
        user = authenticate(request, username=username, password=password)
        if user is None:
            _rate_limited(rate_key, 10, 300, increment=True)
            return _json_error("Неверный логин или пароль")
        ban = find_matching_ban(request, user)
        if ban:
            log_action(request, "login_blocked", actor=user, details={"ban_id": ban.id, "kind": ban.kind})
            return JsonResponse(public_ban_payload(ban), status=403)
        cache.delete(_rate_cache_key(rate_key))
        login(request, user)
        record_client_trace(request, user)
        log_action(request, 'login', actor=user, details={'username': user.username, 'is_staff': user.is_staff})
        return JsonResponse({
            "ok": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.get_display_name(),
                "avatar": user.avatar.url if user.avatar else None,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
            },
        })


# ── /api/auth/register ────────────────────────────────────────────────────────────

class ApiRegister(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except Exception:
            return _json_error("Invalid JSON")
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        register_key = f"register:{get_client_ip(request)}"
        if _rate_limited(register_key, 5, 3600):
            return _json_error("Слишком много регистраций. Попробуйте позже.", 429)
        if len(username) < 3 or len(username) > 16:
            return _json_error("Username: от 3 до 16 символов")
        # Только буквы, цифры, _, -
        import re
        if not re.match(r'^[\w\-]+$', username):
            return _json_error("Username: только буквы, цифры, _ и -")
        if User.objects.filter(username__iexact=username).exists():
            return _json_error("Имя уже занято")
        candidate = User(username=username)
        password_error = _password_error(password, candidate)
        if password_error:
            return _json_error(password_error)
        user = User.objects.create_user(username=username, password=password)
        _rate_limited(register_key, 5, 3600, increment=True)
        login(request, user)
        record_client_trace(request, user)
        log_action(request, 'register', actor=user, details={'username': user.username})
        return JsonResponse({
            "ok": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.get_display_name(),
                "avatar": user.avatar.url if user.avatar else None,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
            },
        })


# ── /api/auth/logout ──────────────────────────────────────────────────────────────

class ApiLogout(View):
    def post(self, request):
        _uname = request.user.username if request.user.is_authenticated else None
        log_action(request, 'logout', details={'username': _uname})
        logout(request)
        return JsonResponse({"ok": True})


# ── /api/board ────────────────────────────────────────────────────────────────────

def api_board(request):
    err = _require_auth(request)
    if err:
        return err
    _sync_tasks_file_safe()
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
            "points": t.get_current_points(),
            "base_points": t.points,
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

class ApiSubmit(View):
    def post(self, request):
        err = _require_auth(request)
        if err:
            return err
        _sync_tasks_file_safe()
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
            log_action(request, 'submit_wrong', details={'username': request.user.username, 'flag_len': len(raw_flag)})
            return JsonResponse({"ok": False, "error": "Неверный флаг", "category": "error"})
        current_pts = task.get_current_points()
        solve, created = Solve.objects.get_or_create(
            user=request.user,
            task=task,
            defaults={"points_awarded": current_pts},
        )
        if not created:
            return JsonResponse({
                "ok": False,
                "error": f"{task.name} уже решён",
                "category": "info",
            })
        log_action(request, 'submit_correct', target_task=task, details={
            'task_id': task.task_id, 'task_name': task.name,
            'category': task.category, 'points_awarded': current_pts, 'base_points': task.points,
        })
        return JsonResponse({
            "ok": True,
            "message": f"Засчитано! {task.name} (+{current_pts} pts)",
            "task_id": task.task_id,
            "points": current_pts,
        })


# ── /api/task-file/<task_id> ──────────────────────────────────────────────────────

def api_task_file(request, task_id: int):
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "error": "Not authenticated"}, status=401)
    _sync_tasks_file_safe()
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
    _sync_tasks_file_safe()
    try:
        u = User.objects.get(username__iexact=username)
    except User.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Пользователь не найден"}, status=404)
    solves = u.solves.select_related("task").order_by("solved_at")
    solved_tasks = []
    cumulative = 0
    for s in solves:
        if not s.task.active:
            continue
        pts = s.points_awarded if s.points_awarded else s.task.points
        cumulative += pts
        solved_tasks.append({
            "task_id": s.task.task_id,
            "name": s.task.name,
            "category": s.task.category,
            "points": pts,
            "base_points": s.task.points,
            "solved_at": str(s.solved_at),
            "cumulative_score": cumulative,
        })
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
        _old_display = user.display_name or ''
        _old_bio = user.bio or ''
        user.display_name = display_name
        user.bio = bio
        if avatar_file:
            try:
                sanitized_avatar = _sanitize_avatar(avatar_file)
            except ValidationError as exc:
                return _json_error(" ".join(exc.messages))
            if user.avatar:
                # Удаляем старый файл
                try:
                    old_path = user.avatar.path
                    if os.path.isfile(old_path):
                        os.remove(old_path)
                except Exception:
                    pass
            user.avatar = sanitized_avatar
        user.save()
        _pf_changes = {}
        if _old_display != (display_name or ''):
            _pf_changes['display_name'] = {'from': _old_display, 'to': display_name or ''}
        if _old_bio != (bio or ''):
            _pf_changes['bio'] = {'from': _old_bio, 'to': bio or ''}
        log_action(request, 'profile_update', actor=user, details={
            'changes': _pf_changes,
            'avatar_changed': bool(avatar_file),
        })
        return JsonResponse({
            "ok": True,
            "display_name": user.get_display_name(),
            "avatar": user.avatar.url if user.avatar else None,
            "bio": user.bio,
        })


# ── /api/profile/change-password ─────────────────────────────────────────────────

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
        password_error = _password_error(new_pw, request.user)
        if password_error:
            return _json_error(password_error)
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
    can_manage_security = request.user.is_superuser
    def active_ban_details(user):
        if not can_manage_security:
            return []
        bans = user.security_bans.filter(active=True).filter(
            Q(expires_at=None) | Q(expires_at__gt=timezone.now())
        ).order_by("kind", "-created_at")
        return [{
            "id": ban.id,
            "kind": ban.kind,
            "kind_label": BAN_KIND_LABELS.get(ban.kind, ban.kind),
            "value": ban.value if ban.kind == SecurityBan.IP else (ban.value[:12] + "…" if ban.value else "аккаунт"),
            "reason": ban.reason or "Причина не указана",
            "expires_at": ban.expires_at.isoformat() if ban.expires_at else None,
        } for ban in bans]

    return JsonResponse({"ok": True, "can_manage_security": can_manage_security, "users": [
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
            "is_active": u.is_active,
            "active_bans": u.security_bans.filter(active=True).filter(Q(expires_at=None) | Q(expires_at__gt=timezone.now())).count() if can_manage_security else 0,
            "active_ban_details": active_ban_details(u),
            "last_ips": list(u.client_traces.exclude(ip=None).values_list("ip", flat=True).distinct()[:5]) if can_manage_security else [],
        }
        for u in users
    ]})


class ApiSuperuserBanUser(View):
    """Ban an account alone, or the account plus its observed secondary signals."""

    def post(self, request, user_id):
        err = _require_superuser(request)
        if err:
            return err
        data = _parse_json(request)
        if data is None:
            return _json_error("Invalid JSON")
        try:
            target = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return _json_error("Пользователь не найден", 404)
        if target.pk == request.user.pk:
            return _json_error("Нельзя заблокировать собственную учётную запись")

        mode = data.get("mode", "account")
        if mode not in {"account", "all_traces"}:
            return _json_error("Неизвестный режим блокировки")
        reason = str(data.get("reason", ""))[:300]
        expires_at = None
        if data.get("expires_hours") not in (None, ""):
            try:
                hours = int(data["expires_hours"])
            except (TypeError, ValueError):
                return _json_error("expires_hours должен быть числом")
            if not 1 <= hours <= 8760:
                return _json_error("Срок блокировки: от 1 до 8760 часов")
            expires_at = timezone.now() + timedelta(hours=hours)

        rules = [(SecurityBan.ACCOUNT, target, "")]
        if mode == "all_traces":
            for trace in target.client_traces.all()[:100]:
                if trace.ip:
                    suffix = 32 if ":" not in trace.ip else 128
                    rules.append((SecurityBan.IP, target, f"{trace.ip}/{suffix}"))
                if trace.signature_hash:
                    rules.append((SecurityBan.SIGNATURE, target, trace.signature_hash))

        created_ids = []
        with transaction.atomic():
            for kind, user, value in dict.fromkeys(rules):
                ban = SecurityBan.objects.filter(kind=kind, user=user, value=value, active=True).first()
                if ban and not ban.is_effective:
                    ban.reason = reason
                    ban.expires_at = expires_at
                    ban.created_by = request.user
                    ban.created_at = timezone.now()
                    ban.save(update_fields=["reason", "expires_at", "created_by", "created_at"])
                elif not ban:
                    ban = SecurityBan(
                        kind=kind, user=user, value=value, reason=reason,
                        expires_at=expires_at, created_by=request.user,
                    )
                    ban.full_clean()
                    ban.save()
                created_ids.append(ban.id)
        sessions = revoke_user_sessions(target.id)
        log_action(request, "ban_created", target_user=target, details={
            "mode": mode, "ban_ids": created_ids, "reason": reason,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "sessions_revoked": sessions,
        })
        return JsonResponse({"ok": True, "ban_ids": created_ids, "sessions_revoked": sessions})


class ApiSuperuserResetPassword(View):
    def post(self, request, user_id):
        err = _require_superuser(request)
        if err:
            return err
        data = _parse_json(request)
        if data is None:
            return _json_error("Invalid JSON")
        try:
            target = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return _json_error("Пользователь не найден", 404)
        password = data.get("new_password") or ""
        password_error = _password_error(password, target)
        if password_error:
            return _json_error(password_error)
        target.set_password(password)
        target.save(update_fields=["password"])
        sessions = revoke_user_sessions(target.id)
        log_action(request, "password_reset", target_user=target, details={
            "sessions_revoked": sessions, "target_was_superuser": target.is_superuser,
        })
        return JsonResponse({"ok": True, "sessions_revoked": sessions})


def api_superuser_bans(request):
    err = _require_superuser(request)
    if err:
        return err
    bans = SecurityBan.objects.select_related("user", "created_by")[:500]
    return JsonResponse({"ok": True, "bans": [{
        "id": ban.id,
        "kind": ban.kind,
        "kind_label": BAN_KIND_LABELS.get(ban.kind, ban.kind),
        "username": ban.user.username if ban.user else None,
        "value": ban.value,
        "reason": ban.reason,
        "active": ban.active,
        "expires_at": ban.expires_at.isoformat() if ban.expires_at else None,
        "created_at": ban.created_at.isoformat(),
        "created_by": ban.created_by.username if ban.created_by else None,
    } for ban in bans]})


class ApiSuperuserRevokeBan(View):
    def post(self, request, ban_id):
        err = _require_superuser(request)
        if err:
            return err
        try:
            ban = SecurityBan.objects.select_related("user").get(pk=ban_id)
        except SecurityBan.DoesNotExist:
            return _json_error("Блокировка не найдена", 404)
        ban.active = False
        ban.save(update_fields=["active"])
        target = ban.user
        log_action(request, "ban_revoked", target_user=target, details={"ban_id": ban.id, "kind": ban.kind})
        return JsonResponse({"ok": True})


class api_admin_toggle_staff(View):
    def post(self, request, user_id):
        err = _require_superuser(request)
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
        _act = 'grant_staff' if u.is_staff else 'revoke_staff'
        log_action(request, _act, target_user=u, details={
            'username': u.username, 'display_name': u.get_display_name(),
            'is_staff': u.is_staff, 'changed_by': request.user.username,
        })
        return JsonResponse({"ok": True, "is_staff": u.is_staff})


def api_admin_tasks(request):
    """GET: список всех задач."""
    err = _require_staff(request)
    if err:
        return err
    _sync_tasks_file_safe()
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
        # Снимок для журнала (до изменений)
        _LFIELDS = ('name', 'category', 'difficulty', 'description', 'points', 'flag', 'url', 'active', 'hide_open_button', 'author', 'author_url')
        _old = {f: getattr(task, f) for f in _LFIELDS}
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
        _changes = {}
        for _f in _LFIELDS:
            _nv = getattr(task, _f)
            if _old[_f] != _nv:
                _changes[_f] = {'from': '[скрыт]', 'to': '[изменён]'} if _f == 'flag' else {'from': _old[_f], 'to': _nv}
        log_action(request, 'task_edit', target_task=task, details={
            'task_id': task.task_id, 'name': task.name, 'changes': _changes,
        })
        return JsonResponse({"ok": True})


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
        log_action(request, 'task_create', target_task=task, details={
            'task_id': task.task_id, 'name': task.name, 'category': task.category,
            'difficulty': task.difficulty, 'points': task.points,
            'active': task.active, 'author': task.author or None,
        })
        return JsonResponse({"ok": True, "task_id": task.task_id, "name": task.name})


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
    log_action(request, 'task_delete', details={
        'task_id': task_id, 'name': task.name, 'category': task.category,
        'points': task.points, 'solve_count': task.solve_count, 'active': task.active,
    })
    task.delete()
    dump_tasks_to_json()
    return JsonResponse({"ok": True})


def api_admin_task_clear_solves(request, task_id):
    err = _require_staff(request)
    if err:
        return err
    try:
        task = Task.objects.get(task_id=task_id)
    except Task.DoesNotExist:
        task = None
    n = Solve.objects.filter(task__task_id=task_id).delete()[0]
    log_action(request, 'clear_task_solves', target_task=task, details={
        'task_id': task_id, 'task_name': task.name if task else '?', 'deleted_count': n,
    })
    return JsonResponse({"ok": True, "deleted": n})


def api_admin_reset_solves(request):
    err = _require_staff(request)
    if err:
        return err
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST only"}, status=405)
    n = Solve.objects.all().delete()[0]
    log_action(request, 'reset_all_solves', details={
        'deleted_count': n,
        'reset_by': request.user.username if request.user.is_authenticated else None,
    })
    return JsonResponse({"ok": True, "deleted": n})


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
        log_action(request, 'set_announcement', details={
            'text': text or None,
            'cleared': not bool(text),
        })
        return JsonResponse({"ok": True, "text": text})


def api_admin_dynamic_pricing(request):
    """GET: получить настройки; POST: обновить настройки динамического ценообразования."""
    err = _require_staff(request)
    if err:
        return err
    cfg = DynamicPricingConfig.get_config()
    if request.method == "GET":
        _sync_tasks_file_safe()
        from django.db.models import Count
        tasks_preview = [
            {
                "name": t.name,
                "base": t.points,
                "current": t.get_current_points(),
                "solves": t.sc,
            }
            for t in Task.objects.filter(active=True).annotate(sc=Count("solves"))[:25]
        ]
        return JsonResponse({
            "ok": True,
            "enabled": cfg.enabled,
            "decay_per_solve": cfg.decay_per_solve,
            "min_percent": cfg.min_percent,
            "tasks_preview": tasks_preview,
        })
    elif request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return _json_error("Invalid JSON")
        _old_dp = {'enabled': cfg.enabled, 'decay_per_solve': cfg.decay_per_solve, 'min_percent': cfg.min_percent}
        if "enabled" in data:
            cfg.enabled = bool(data["enabled"])
        if "decay_per_solve" in data:
            try:
                decay = int(data["decay_per_solve"])
            except (ValueError, TypeError):
                return _json_error("decay_per_solve должен быть числом")
            if decay < 0:
                return _json_error("decay_per_solve не может быть отрицательным")
            cfg.decay_per_solve = decay
        if "min_percent" in data:
            try:
                pct = int(data["min_percent"])
            except (ValueError, TypeError):
                return _json_error("min_percent должен быть числом")
            if not (1 <= pct <= 100):
                return _json_error("min_percent должен быть от 1 до 100")
            cfg.min_percent = pct
        _dp_changes = {}
        if _old_dp['enabled'] != cfg.enabled:
            _dp_changes['enabled'] = {'from': _old_dp['enabled'], 'to': cfg.enabled}
        if _old_dp['decay_per_solve'] != cfg.decay_per_solve:
            _dp_changes['decay_per_solve'] = {'from': _old_dp['decay_per_solve'], 'to': cfg.decay_per_solve}
        if _old_dp['min_percent'] != cfg.min_percent:
            _dp_changes['min_percent'] = {'from': _old_dp['min_percent'], 'to': cfg.min_percent}
        cfg.save()
        log_action(request, 'dynamic_pricing_change', details={'changes': _dp_changes})
        return JsonResponse({
            "ok": True,
            "enabled": cfg.enabled,
            "decay_per_solve": cfg.decay_per_solve,
            "min_percent": cfg.min_percent,
        })
    return JsonResponse({"ok": False, "error": "Method not allowed"}, status=405)


_CATEGORY_FOLDER = {
    'Web': 'web',
    'Разное': 'misc',
    'Крипто': 'crypto',
    'Форензика': 'forenzika',
    'Реверс': 'revers',
    'Pwn': 'pwn',
    'ОСИНТ': 'osint',
}


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

        # os.path.basename не обрезает Windows-пути на Linux,
        # поэтому нормализуем оба разделителя вручную
        filename = f.name.replace('\\', '/').split('/')[-1]
        if not re.match(r'^[\w\-. ]+$', filename):
            return _json_error("Недопустимое имя файла (разрешены: буквы, цифры, -, _, пробел, .)")
        if f.size > ApiAdminTaskUploadFile.MAX_SIZE:
            return _json_error("Файл не должен превышать 64 МБ")

        try:
            subdir = _CATEGORY_FOLDER.get(task.category, 'misc')
            task_dir = Path(settings.TASK_FILES_DIR) / subdir
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
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Task file upload failed")
            return _json_error("Ошибка загрузки файла", 500)


def api_admin_audit_log(request):
    """GET: журнал действий с пагинацией и фильтрацией по типу действия."""
    err = _require_staff(request)
    if err:
        return err
    try:
        page  = max(1, int(request.GET.get('page', 1)))
        limit = min(100, max(10, int(request.GET.get('limit', 50))))
    except (ValueError, TypeError):
        page, limit = 1, 50
    action_filter = request.GET.get('action', '').strip()

    qs = AuditLog.objects.select_related('actor', 'target_user', 'target_task').order_by('-timestamp')
    if action_filter:
        qs = qs.filter(action=action_filter)

    total  = qs.count()
    offset = (page - 1) * limit
    entries = qs[offset:offset + limit]

    return JsonResponse({
        'ok':    True,
        'total': total,
        'page':  page,
        'limit': limit,
        'entries': [
            {
                'id':          e.id,
                'timestamp':   e.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'actor':       e.actor.username if e.actor else None,
                'action':      e.action,
                'action_label': dict(AuditLog.ACTION_CHOICES).get(e.action, e.action),
                'target_user': e.target_user.username if e.target_user else None,
                'target_task': e.target_task.name    if e.target_task else None,
                'details':     e.details,
                'ip':          e.ip,
            }
            for e in entries
        ],
        'action_choices': [{'value': '', 'label': 'Все'}] + [
            {'value': v, 'label': l} for v, l in AuditLog.ACTION_CHOICES
        ],
    })


def api_admin_audit_entry(request):
    """POST: клиент сигнализирует о входе в панель администратора."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Method not allowed"}, status=405)
    err = _require_staff(request)
    if err:
        return err
    log_action(request, 'admin_login', actor=request.user)
    return JsonResponse({"ok": True})
