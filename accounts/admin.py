""" Admin definitions """
from django.contrib import admin
from .models import User, TeamMate, UnregisteredUser


class UserAdmin(admin.ModelAdmin):
    """Controls the search fields in the Admin app"""

    search_fields = ("last_name", "system_number", "email")


class TeamMateAdmin(admin.ModelAdmin):
    """Show fields as searches rather than dropdowns"""

    autocomplete_fields = ["user", "team_mate"]


admin.site.register(User, UserAdmin)
admin.site.register(TeamMate, TeamMateAdmin)
admin.site.register(UnregisteredUser, UserAdmin)
