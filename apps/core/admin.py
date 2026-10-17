"""Django admin is a technical fallback for developers; staff use the /manage/ back office."""
from django.apps import apps
from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_repr")
    list_filter = ("action",)
    search_fields = ("object_repr", "actor__email")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "first_name", "last_name", "state", "is_active", "date_joined")
    search_fields = ("email", "first_name", "last_name")
    exclude = ("password",)


def register_all():
    from apps.accounts.models import User

    try:
        admin.site.register(User, UserAdmin)
    except AlreadyRegistered:
        pass
    for label in ("core", "accounts", "institutions", "catalog", "learning", "assessments", "credentials", "commerce",
                  "support", "notifications", "analytics", "web", "practicals", "live", "library", "integrations",
                  "careers", "ai", "labs", "community", "workforce", "research"):
        for model in apps.get_app_config(label).get_models():
            try:
                admin.site.register(model)
            except AlreadyRegistered:
                pass


register_all()
