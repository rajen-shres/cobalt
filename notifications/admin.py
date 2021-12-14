from django.contrib import admin
from .models import (
    InAppNotification,
    NotificationMapping,
    Email,
    EmailArchive,
    EmailThread,
    Snooper,
    BatchID,
    BlockNotification,
    RealtimeNotification,
    RealtimeNotificationHeader,
)


class InAppNotificationAdmin(admin.ModelAdmin):
    search_fields = ("member",)
    autocomplete_fields = ["member"]


class NotificationMappingAdmin(admin.ModelAdmin):
    search_fields = ("member",)
    autocomplete_fields = ["member"]


class RealtimeNotificationAdmin(admin.ModelAdmin):
    search_fields = ("member", "admin")
    autocomplete_fields = ["member", "admin"]


class RealtimeNotificationHeaderAdmin(admin.ModelAdmin):
    search_fields = ("admin",)
    autocomplete_fields = ["admin"]


admin.site.register(InAppNotification, InAppNotificationAdmin)
admin.site.register(NotificationMapping, NotificationMappingAdmin)
admin.site.register(Email)
admin.site.register(EmailArchive)
admin.site.register(EmailThread)
admin.site.register(Snooper)
admin.site.register(BatchID)
admin.site.register(BlockNotification)
admin.site.register(RealtimeNotification, RealtimeNotificationAdmin)
admin.site.register(RealtimeNotificationHeader, RealtimeNotificationHeaderAdmin)
