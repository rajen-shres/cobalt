from django.contrib import admin

from api.models import ApiLog


class ApiLogAdmin(admin.ModelAdmin):

    autocomplete_fields = ["admin"]


admin.site.register(ApiLog, ApiLogAdmin)
