from django.contrib import admin

from club_sessions.models import (
    Session,
    SessionType,
    SessionTypePaymentMethod,
    SessionEntry,
    SessionTypePaymentMethodMembership,
)


class SessionTypeAdmin(admin.ModelAdmin):

    search_fields = ["name", "organisation"]
    autocomplete_fields = ["organisation"]


class SessionTypePaymentMethodAdmin(admin.ModelAdmin):

    search_fields = ["name", "organisation"]
    autocomplete_fields = ["organisation"]


admin.site.register(Session)
admin.site.register(SessionType, SessionTypeAdmin)
admin.site.register(SessionTypePaymentMethod)
admin.site.register(SessionEntry)
admin.site.register(SessionTypePaymentMethodMembership)
