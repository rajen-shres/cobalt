from django.contrib import admin
from .models import (
    Organisation,
    MemberMembershipType,
    MembershipType,
    ClubLog,
    MemberClubEmail,
    ClubTag,
    MemberClubTag,
    OrganisationFrontPage,
    OrgVenue,
)


class OrganisationAdmin(admin.ModelAdmin):
    search_fields = ["name"]


admin.site.register(Organisation, OrganisationAdmin)
admin.site.register(MemberMembershipType)
admin.site.register(MembershipType)
admin.site.register(MemberClubEmail)
admin.site.register(ClubLog)
admin.site.register(ClubTag)
admin.site.register(MemberClubTag)
admin.site.register(OrganisationFrontPage)
admin.site.register(OrgVenue)
