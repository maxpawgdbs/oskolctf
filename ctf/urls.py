from django.urls import path
from ctf import api_views, views

urlpatterns = [
    # ── SPA (все страницы через Vue Router) ─────────────────────────────────
    path("", views.spa, name="home"),
    path("login/", views.spa),
    path("register/", views.spa),
    path("board/", views.spa),
    path("profile/", views.spa),
    path("profile/<str:username>/", views.spa),
    # ── Кастомная admin SPA ──────────────────────────────────────────────────
    path("ctf-admin/", views.spa),

    # ── Веб-задания ──────────────────────────────────────────────────────────
    path("task0", views.task0),
    path("task1", views.task1),
    path("task2", views.task2),
    path("task3", views.task3),
    path("task4", views.task4),
    path("task5", views.task5),
    path("flag", views.secret_flag),
    path("logout", views.logout_view),

    # ── API ──────────────────────────────────────────────────────────────────
    path("api/me", api_views.api_me),
    path("api/csrf", api_views.api_csrf),
    path("api/board", api_views.api_board),
    path("api/task-file/<int:task_id>", api_views.api_task_file),
    # profile/update и change-password — ДО <str:username>, иначе Django съедает как username
    path("api/profile/update", api_views.ApiProfileUpdate.as_view()),
    path("api/profile/change-password", api_views.ApiChangePassword.as_view()),
    path("api/profile/<str:username>", api_views.api_profile),
    path("api/auth/login", api_views.ApiLogin.as_view()),
    path("api/auth/register", api_views.ApiRegister.as_view()),
    path("api/auth/logout", api_views.ApiLogout.as_view()),
    path("api/submit", api_views.ApiSubmit.as_view()),
    path("api/announcement", api_views.api_announcement),
    # Admin API
    path("api/admin/stats", api_views.api_admin_stats),
    path("api/admin/sync-tasks", api_views.ApiAdminSyncTasks.as_view()),
    path("api/admin/users", api_views.api_admin_users),
    path("api/admin/users/<int:user_id>/toggle-staff", api_views.api_admin_toggle_staff.as_view()),
    path("api/admin/users/<int:user_id>/ban", api_views.ApiSuperuserBanUser.as_view()),
    path("api/admin/users/<int:user_id>/reset-password", api_views.ApiSuperuserResetPassword.as_view()),
    path("api/admin/security/bans", api_views.api_superuser_bans),
    path("api/admin/security/bans/<int:ban_id>/revoke", api_views.ApiSuperuserRevokeBan.as_view()),
    path("api/admin/tasks-list", api_views.api_admin_tasks),
    path("api/admin/tasks/create", api_views.ApiAdminTaskCreate.as_view()),
    path("api/admin/tasks/<int:task_id>/save", api_views.ApiAdminTaskSave.as_view()),
    path("api/admin/tasks/<int:task_id>/upload-file", api_views.ApiAdminTaskUploadFile.as_view()),
    path("api/admin/tasks/<int:task_id>/clear-solves", api_views.api_admin_task_clear_solves),
    path("api/admin/tasks/<int:task_id>/delete", api_views.api_admin_task_delete),
    path("api/admin/reset-solves", api_views.api_admin_reset_solves),
    path("api/admin/set-announcement", api_views.ApiAdminSetAnnouncement.as_view()),
    path("api/admin/dynamic-pricing", api_views.api_admin_dynamic_pricing),
    path("api/admin/audit-log", api_views.api_admin_audit_log),
    path("api/admin/audit-entry", api_views.api_admin_audit_entry),
]
