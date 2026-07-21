import hashlib
import ipaddress

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db.models import F
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone

from ctf.models import ClientTrace, SecurityBan


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


class SecurityBanMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ban = find_matching_ban(request, getattr(request, "user", None))
        if ban:
            payload = {"ok": False, "error": "Access denied", "code": "banned"}
            if request.path.startswith("/api/"):
                return JsonResponse(payload, status=403)
            return HttpResponseForbidden("Access denied")
        return self.get_response(request)
