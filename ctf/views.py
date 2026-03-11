"""
Веб-вьюхи: SPA, задания (task0–task4), профиль страницы.
"""
import os
from pathlib import Path
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden
from django.contrib.auth import logout as auth_logout
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ctf.models import Task


# ── SPA ──────────────────────────────────────────────────────────────────────────

def spa(request, **kwargs):
    """Отдаёт SPA (Vue.js). Читаем файл напрямую — Django Template Engine не трогает {{ }}."""
    content = (Path(settings.BASE_DIR) / "templates" / "spa.html").read_text(encoding="utf-8")
    return HttpResponse(content, content_type="text/html; charset=utf-8")


# ── Задания ───────────────────────────────────────────────────────────────────────

def _get_flag(task_id: int) -> str:
    try:
        return Task.objects.get(task_id=task_id).flag.strip()
    except Task.DoesNotExist:
        return ""


def task0(request):
    flag = _get_flag(0)
    return HttpResponse(f"<h1>Привет! Это твой первый флаг! {flag}</h1>")


def task1(request):
    flag = _get_flag(1)
    return render(request, "task1.html", {"flag": flag})


def task2(request):
    flag = _get_flag(2)
    response = render(request, "task2.html")
    response.set_cookie("flag", flag, max_age=86400)
    return response


@csrf_exempt
@require_http_methods(["GET", "POST"])
def task3(request):
    if request.method == "GET":
        return render(request, "task3.html")
    data = request.body.decode("utf-8")
    if data == "b3Nrb2xjdGY=":
        return HttpResponse(_get_flag(3))
    return HttpResponse("<h1>Wrong data, try again!</h1>")


@csrf_exempt
def task4(request):
    if request.COOKIES.get("xorg_worship_flag_for_you") == "true":
        return HttpResponse(_get_flag(4))
    response = HttpResponse("<h1>Я сам решал это 3 дня...</h1>")
    response.set_cookie("xorg_worship_flag_for_you", "false", max_age=86400)
    return response


def task5(request):
    flag = _get_flag(5)
    return HttpResponse(f"<h1>Секретная тропа! {flag}</h1>")


# ── Пасхалка ─────────────────────────────────────────────────────────────────────

def secret_flag(request):
    return HttpResponse("<h1>Ты нашёл секретный флаг! oskolctf{oskolctf}</h1>")


# ── Logout ────────────────────────────────────────────────────────────────────────

def logout_view(request):
    auth_logout(request)
    return redirect("/")
