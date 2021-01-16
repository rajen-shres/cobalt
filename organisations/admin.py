from django.contrib import admin
from .models import Organisation, MemberOrganisation

class OrganisationAdmin(admin.ModelAdmin):
    search_fields = ['name']

admin.site.register(Organisation, OrganisationAdmin)
admin.site.register(MemberOrganisation)
