""" Admin definitions """
from django.contrib import admin
from .models import User, TeamMate, UnregisteredUser, APIToken, UserAdditionalInfo


class UserAdmin(admin.ModelAdmin):
    """Controls the search fields in the Admin app"""

    search_fields = ("last_name", "system_number", "email", "pk")
    change_form_template = "loginas/change_form.html"


class TeamMateAdmin(admin.ModelAdmin):
    """Show fields as searches rather than dropdowns"""

    autocomplete_fields = ["user", "team_mate"]


class APITokenAdmin(admin.ModelAdmin):
    """Show fields as searches rather than dropdowns"""

    autocomplete_fields = ["user"]


class UserAdditionalInfoAdmin(admin.ModelAdmin):
    """Show fields as searches rather than dropdowns"""

    autocomplete_fields = ["user"]


admin.site.register(User, UserAdmin)
admin.site.register(TeamMate, TeamMateAdmin)
admin.site.register(UnregisteredUser, UserAdmin)
admin.site.register(APIToken, APITokenAdmin)
admin.site.register(UserAdditionalInfo, UserAdditionalInfoAdmin)
