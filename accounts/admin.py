""" Admin definitions """
from django.contrib import admin
from .models import User, TeamMate


class UserAdmin(admin.ModelAdmin):
    """ Controls the search fields in the Admin app """

    search_fields = ("last_name", "system_number", "email")


admin.site.register(User, UserAdmin)
admin.site.register(TeamMate)
