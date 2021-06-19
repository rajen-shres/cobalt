from django.contrib import admin
from .models import (
    RBACGroup,
    RBACUserGroup,
    RBACGroupRole,
    RBACAdminGroup,
    RBACAdminUserGroup,
    RBACAdminGroupRole,
    RBACModelDefault,
    RBACAppModelAction,
    RBACAdminTree,
)


class RBACGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "name_qualifier", "name_item", "description")
    search_fields = ("name_qualifier", "name_item", "description")


class RBACUserGroupAdmin(admin.ModelAdmin):
    list_display = ("group", "member")
    search_fields = (
        "group__description",
        "group__name_qualifier",
        "group__name_item",
        "member__first_name",
        "member__last_name",
    )


class RBACGroupRoleAdmin(admin.ModelAdmin):
    list_display = (
        "group",
        "role",
        "action",
        "rule_type",
    )
    search_fields = (
        "group__name",
        "role",
    )


class RBACAdminGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "name_qualifier", "name_item", "description")
    search_fields = ("name_qualifier", "name_item", "description")


class RBACAdminUserGroupAdmin(admin.ModelAdmin):
    list_display = ("group", "member")
    search_fields = (
        "group__description",
        "group__name_qualifier",
        "group__name_item",
        "member__first_name",
        "member__last_name",
    )


class RBACAdminGroupRoleAdmin(admin.ModelAdmin):
    list_display = (
        "group",
        "app",
        "model",
        "model_id",
    )
    search_fields = (
        "group__name_item",
        "app",
    )


class RBACModelDefaultAdmin(admin.ModelAdmin):
    list_display = (
        "app",
        "model",
        "default_behaviour",
    )
    search_fields = ("app", "model", "default_behaviour")


class RBACAppModelActionAdmin(admin.ModelAdmin):
    list_display = (
        "app",
        "model",
        "valid_action",
        "description",
    )
    search_fields = (
        "app",
        "model",
        "valid_action",
        "description",
    )


class RBACAdminTreeAdmin(admin.ModelAdmin):
    list_display = ("group", "tree")
    search_fields = (
        "group__description",
        "group__name_qualifier",
        "group__name_item",
        "tree",
    )


admin.site.register(RBACGroup, RBACGroupAdmin)
admin.site.register(RBACUserGroup, RBACUserGroupAdmin)
admin.site.register(RBACGroupRole, RBACGroupRoleAdmin)
admin.site.register(RBACAdminGroup, RBACAdminGroupAdmin)
admin.site.register(RBACAdminUserGroup, RBACAdminUserGroupAdmin)
admin.site.register(RBACAdminGroupRole, RBACAdminGroupRoleAdmin)
admin.site.register(RBACModelDefault, RBACModelDefaultAdmin)
admin.site.register(RBACAppModelAction, RBACAppModelActionAdmin)
admin.site.register(RBACAdminTree, RBACAdminTreeAdmin)
