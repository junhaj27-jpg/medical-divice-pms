from django.contrib import admin

from .market_models import MarketAccess
from .services import audit


@admin.register(MarketAccess)
class MarketAccessAdmin(admin.ModelAdmin):
    list_display = ("user", "markets")
    search_fields = ("user__username",)

    def has_delete_permission(self, request, obj=None):
        # Revoke by saving an empty list; deleting would turn off account scoping.
        return False

    def save_model(self, request, obj, form, change):
        before = MarketAccess.objects.filter(pk=obj.pk).values("markets").first() if change else {}
        super().save_model(request, obj, form, change)
        audit(request.user, "MARKET_GRANTS", obj, before=before,
              after={"user_id": obj.user_id, "markets": obj.markets})

    def get_readonly_fields(self, request, obj=None):
        return ("user",) if obj else ()
