# pylint: disable=missing-module-docstring,missing-class-docstring
from django.contrib import admin
from .models import (
    StripeTransaction,
    MemberTransaction,
    OrganisationTransaction,
    StripeLog,
    PaymentStatic,
    OrganisationSettlementFees,
    OrgPaymentMethod,
    UserPendingPayment,
)


class MemberTransactionAdmin(admin.ModelAdmin):
    search_fields = ["reference_no", "type"]


class OrganisationTransactionAdmin(admin.ModelAdmin):
    search_fields = ["reference_no", "type"]


class StripeTransactionAdmin(admin.ModelAdmin):
    search_fields = ["stripe_reference"]
    list_display = ["member", "status", "amount", "refund_amount"]


class StripeLogAdmin(admin.ModelAdmin):
    search_fields = ["event"]


admin.site.register(MemberTransaction, MemberTransactionAdmin)
admin.site.register(OrganisationTransaction, OrganisationTransactionAdmin)
admin.site.register(StripeTransaction, StripeTransactionAdmin)
admin.site.register(StripeLog, StripeLogAdmin)
admin.site.register(OrganisationSettlementFees)
admin.site.register(PaymentStatic)
admin.site.register(OrgPaymentMethod)
admin.site.register(UserPendingPayment)
