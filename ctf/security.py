import hashlib
import ipaddress

from django.conf import settings
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.sessions.models import Session
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from ctf.models import ClientTrace, SecurityBan


BAN_KIND_LABELS = {
    SecurityBan.ACCOUNT: "аккаунт",
    SecurityBan.IP: "IP-адрес",
    SecurityBan.SIGNATURE: "сигнатура браузера",
    SecurityBan.USER_AGENT: "отпечаток браузера",
}


def public_ban_payload(ban) -> dict:
    kind_label = BAN_KIND_LABELS.get(ban.kind, "правило безопасности")
    return {
        "ok": False,
        "error": f"Доступ заблокирован: {kind_label}",
        "code": "banned",
        "ban": {
            "reference": ban.id,
            "kind": ban.kind,
            "kind_label": kind_label,
            "reason": ban.reason or "Причина не указана",
            "expires_at": ban.expires_at.isoformat() if ban.expires_at else None,
            "permanent": ban.expires_at is None,
        },
    }


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest() if value else ""


def get_client_ip(request) -> str | None:
    """Trust the proxy header only when the deployment explicitly enables it."""
    value = request.META.get("REMOTE_ADDR", "")
    if getattr(settings, "TRUST_PROXY_HEADERS", False):
        value = request.META.get("HTTP_X_REAL_IP", "") or value
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def get_request_signals(request) -> dict:
    signature = request.headers.get("X-Client-Signature", "")[:512]
    user_agent = request.headers.get("User-Agent", "")[:2048]
    return {
        "ip": get_client_ip(request),
        "signature_hash": _sha256(signature),
        "user_agent_hash": _sha256(user_agent),
    }


def record_client_trace(request, user) -> None:
    signals = get_request_signals(request)
    trace, created = ClientTrace.objects.get_or_create(user=user, **signals)
    if not created:
        ClientTrace.objects.filter(pk=trace.pk).update(
            last_seen=timezone.now(), seen_count=F("seen_count") + 1
        )


def find_matching_ban(request, user=None):
    now = timezone.now()
    bans = SecurityBan.objects.filter(active=True).filter(
        models_q_not_expired(now)
    ).select_related("user")
    if user and user.is_authenticated:
        match = bans.filter(kind=SecurityBan.ACCOUNT, user=user).first()
        if match:
            return match

    signals = get_request_signals(request)
    if signals["signature_hash"]:
        match = bans.filter(kind=SecurityBan.SIGNATURE, value=signals["signature_hash"]).first()
        if match:
            return match
    if signals["user_agent_hash"]:
        match = bans.filter(kind=SecurityBan.USER_AGENT, value=signals["user_agent_hash"]).first()
        if match:
            return match
    if signals["ip"]:
        address = ipaddress.ip_address(signals["ip"])
        for ban in bans.filter(kind=SecurityBan.IP):
            try:
                if address in ipaddress.ip_network(ban.value, strict=False):
                    return ban
            except ValueError:
                continue
    return None


def models_q_not_expired(now):
    from django.db.models import Q

    return Q(expires_at__isnull=True) | Q(expires_at__gt=now)


def revoke_user_sessions(user_id: int) -> int:
    deleted = 0
    for session in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        try:
            if str(session.get_decoded().get("_auth_user_id")) == str(user_id):
                session.delete()
                deleted += 1
        except Exception:
            continue
    return deleted


def get_session_user_for_ban_check(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user
    try:
        user_id = request.session.get(SESSION_KEY)
    except Exception:
        return user
    if not user_id:
        return user
    try:
        return get_user_model().objects.filter(pk=user_id).first() or user
    except Exception:
        return user


class SecurityBanMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ban = find_matching_ban(request, get_session_user_for_ban_check(request))
        if ban:
            payload = public_ban_payload(ban)
            if request.path.startswith("/api/"):
                return JsonResponse(payload, status=403)
            return render(request, "blocked.html", {"ban": payload["ban"]}, status=403)
        return self.get_response(request)
