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
)


class InAppNotificationAdmin(admin.ModelAdmin):
    search_fields = ("member",)


class NotificationMappingAdmin(admin.ModelAdmin):
    search_fields = ("member",)


admin.site.register(InAppNotification, InAppNotificationAdmin)
admin.site.register(NotificationMapping, NotificationMappingAdmin)

admin.site.register(Email)
admin.site.register(EmailArchive)
admin.site.register(EmailThread)
admin.site.register(Snooper)
admin.site.register(BatchID)
admin.site.register(BlockNotification)
