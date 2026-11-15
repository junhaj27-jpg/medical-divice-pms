from copy import deepcopy
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Max
from .dental_models import WritingTemplate
from .services import audit, role


@admin.register(WritingTemplate)
class WritingTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "version", "state", "example", "market", "pathway")
    actions = ("clone_version",)
    save_as = False

    def has_module_permission(self, request):
        return role(request.user) == "ADMIN"

    def has_view_permission(self, request, obj=None):
        return role(request.user) == "ADMIN"

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in WritingTemplate._meta.fields if field.name != "id") if obj and obj.state == "PUBLISHED" else ()

    def save_model(self, request, obj, form, change):
        if role(request.user) != "ADMIN":
            raise PermissionDenied
        obj.save()
        audit(request.user, "WRITING_TEMPLATE", obj, after={"state": obj.state, "version": obj.version})

    @admin.action(description="새 초안 버전으로 복제")
    def clone_version(self, request, queryset):
        if role(request.user) != "ADMIN":
            raise PermissionDenied
        for template in queryset:
            values = {f.name: deepcopy(getattr(template, f.name)) for f in template._meta.fields if f.name != "id"}
            values.update(state="DRAFT", version=(WritingTemplate.objects.filter(key=template.key).aggregate(v=Max("version"))["v"] or 0) + 1)
            cloned = WritingTemplate.objects.create(**values)
            audit(request.user, "WRITING_TEMPLATE_CLONE", cloned)
