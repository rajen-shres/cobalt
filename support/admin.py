from django.contrib import admin
from .models import (
    Incident,
    IncidentLineItem,
    Attachment,
)


class IncidentAdmin(admin.ModelAdmin):
    list_display = ("reported_by_user", "reported_by_email", "description")
    search_fields = ("reported_by_user", "reported_by_email", "description")


class IncidentLineItemAdmin(admin.ModelAdmin):
    list_display = ("staff", "created_date", "incident")
    search_fields = ("staff", "description", "incident")


admin.site.register(Incident, IncidentAdmin)
admin.site.register(IncidentLineItem, IncidentLineItemAdmin)
admin.site.register(Attachment)
