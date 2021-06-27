from django.contrib import admin
from .models import (
    Incident,
)


class IncidentAdmin(admin.ModelAdmin):
    list_display = ("reported_by_user", "reported_by_email", "description")
    search_fields = ("reported_by_user", "reported_by_email", "description")


admin.site.register(Incident, IncidentAdmin)
