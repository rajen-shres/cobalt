from django.contrib import admin
from .models import InAppNotification, NotificationMapping, Email, EmailArchive


class InAppNotificationAdmin(admin.ModelAdmin):
    search_fields = ("member",)


class NotificationMappingAdmin(admin.ModelAdmin):
    search_fields = ("member",)


admin.site.register(InAppNotification, InAppNotificationAdmin)
admin.site.register(NotificationMapping, NotificationMappingAdmin)

admin.site.register(Email)
admin.site.register(EmailArchive)
