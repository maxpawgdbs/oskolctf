import json
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from ctf.models import AuditLog, SecurityBan, User


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    TRUST_PROXY_HEADERS=False,
)
class SecurityControlTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser("root", password="StrongRootPass!42")
        self.staff = User.objects.create_user("staff", password="StrongStaffPass!42", is_staff=True)
        self.user = User.objects.create_user("player", password="StrongPlayerPass!42")

    def csrf_client(self, user=None):
        client = Client(enforce_csrf_checks=True)
        if user:
            client.force_login(user)
        response = client.get("/api/csrf")
        token = response.json()["csrf"]
        return client, token

    def post(self, client, token, url, payload):
        return client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_X_CLIENT_SIGNATURE="test-browser-signature",
            HTTP_USER_AGENT="security-test-agent",
        )

    def test_login_requires_csrf(self):
        response = Client(enforce_csrf_checks=True).post(
            "/api/auth/login",
            data=json.dumps({"username": "player", "password": "StrongPlayerPass!42"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_cannot_ban_or_reset_password(self):
        client, token = self.csrf_client(self.staff)
        ban = self.post(client, token, f"/api/admin/users/{self.user.id}/ban", {"mode": "account"})
        reset = self.post(
            client, token, f"/api/admin/users/{self.user.id}/reset-password",
            {"new_password": "AnotherStrongPass!42"},
        )
        self.assertEqual(ban.status_code, 403)
        self.assertEqual(reset.status_code, 403)

    def test_superuser_ban_revokes_existing_session(self):
        victim = Client()
        victim.force_login(self.user)
        admin, token = self.csrf_client(self.superuser)
        response = self.post(
            admin, token, f"/api/admin/users/{self.user.id}/ban",
            {"mode": "account", "reason": "test"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(SecurityBan.objects.filter(user=self.user, active=True).exists())
        self.assertEqual(body["created_rules"][0]["kind_label"], "аккаунт")
        self.assertEqual(body["created_rules"][0]["reason"], "test")
        self.assertEqual(victim.get("/api/me").status_code, 200)
        self.assertIsNone(victim.get("/api/me").json()["user"])
        relogin, relogin_token = self.csrf_client()
        blocked_login = self.post(
            relogin, relogin_token, "/api/auth/login",
            {"username": "player", "password": "StrongPlayerPass!42"},
        )
        self.assertEqual(blocked_login.status_code, 403)
        self.assertEqual(blocked_login.json()["ban"]["kind_label"], "аккаунт")
        self.assertEqual(blocked_login.json()["ban"]["reason"], "test")
        audit = AuditLog.objects.filter(action="login_blocked").latest("id")
        self.assertEqual(audit.details["kind_label"], "аккаунт")
        self.assertEqual(audit.details["reason"], "test")

    def test_superuser_can_reset_admin_password_and_sessions(self):
        staff_client = Client()
        staff_client.force_login(self.staff)
        admin, token = self.csrf_client(self.superuser)
        response = self.post(
            admin, token, f"/api/admin/users/{self.staff.id}/reset-password",
            {"new_password": "AnotherStrongPass!42"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["target_username"], "staff")
        self.assertEqual(response.json()["target_role"], "admin")
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password("AnotherStrongPass!42"))
        self.assertFalse(self.staff.check_password("StrongStaffPass!42"))
        self.assertIsNone(staff_client.get("/api/me").json()["user"])
        audit = AuditLog.objects.filter(action="password_reset").latest("id")
        self.assertEqual(audit.details["target_username"], "staff")
        self.assertEqual(audit.details["target_role"], "admin")

    def test_login_records_hashed_trace_and_ignores_xff_by_default(self):
        client, token = self.csrf_client()
        response = self.post(
            client, token, "/api/auth/login",
            {"username": "player", "password": "StrongPlayerPass!42"},
        )
        self.assertEqual(response.status_code, 200)
        trace = self.user.client_traces.get()
        self.assertNotEqual(trace.signature_hash, "")
        self.assertNotEqual(trace.user_agent_hash, "")
        self.assertEqual(trace.ip, "127.0.0.1")

    def test_avatar_mime_spoof_is_rejected(self):
        client, token = self.csrf_client(self.user)
        fake = SimpleUploadedFile("avatar.png", b"<script>alert(1)</script>", content_type="image/png")
        response = client.post(
            "/api/profile/update",
            {"display_name": "Player", "bio": "", "avatar": fake},
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    def test_create_superusers_upgrades_existing_named_accounts(self):
        existing = User.objects.create_user("nekoty", password="OldStrongPass!42", is_staff=False, is_superuser=False)
        with override_settings(DEBUG=False):
            with patch.dict("os.environ", {"SUPERUSER_PASSWORD": "StrongRootPass!42"}):
                call_command("create_superusers")
        existing.refresh_from_db()
        self.assertTrue(existing.is_staff)
        self.assertTrue(existing.is_superuser)
        self.assertTrue(existing.is_active)

    def test_trace_ban_blocks_observed_ip_and_signature(self):
        victim = Client(enforce_csrf_checks=True)
        token = victim.get("/api/csrf", REMOTE_ADDR="203.0.113.10").json()["csrf"]
        login_response = victim.post(
            "/api/auth/login",
            data=json.dumps({"username": "player", "password": "StrongPlayerPass!42"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_X_CLIENT_SIGNATURE="victim-signature",
            HTTP_USER_AGENT="victim-agent",
            REMOTE_ADDR="203.0.113.10",
        )
        self.assertEqual(login_response.status_code, 200)

        admin, admin_token = self.csrf_client(self.superuser)
        response = self.post(
            admin, admin_token, f"/api/admin/users/{self.user.id}/ban",
            {"mode": "all_traces", "reason": "abuse"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(SecurityBan.objects.filter(kind=SecurityBan.IP, value="203.0.113.10/32").exists())
        self.assertTrue(SecurityBan.objects.filter(kind=SecurityBan.SIGNATURE).exists())

        blocked = Client().get(
            "/api/csrf",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_CLIENT_SIGNATURE="new-signature",
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["ban"]["kind_label"], "IP-адрес")
        self.assertEqual(blocked.json()["ban"]["reason"], "abuse")
        blocked_post = Client(enforce_csrf_checks=True).post(
            "/api/auth/register",
            data=json.dumps({"username": "newplayer", "password": "StrongNewPass!42"}),
            content_type="application/json",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_CLIENT_SIGNATURE="new-signature",
        )
        self.assertEqual(blocked_post.status_code, 403)
        self.assertEqual(blocked_post.json()["ban"]["kind_label"], "IP-адрес")
        blocked_page = Client().get("/", REMOTE_ADDR="203.0.113.10")
        self.assertContains(blocked_page, "IP-адрес", status_code=403)
        self.assertContains(blocked_page, "abuse", status_code=403)
