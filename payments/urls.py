# pylint: disable=missing-module-docstring,missing-class-docstring
from django.urls import path
from . import views
from . import core

app_name = "payments"  # pylint: disable=invalid-name

urlpatterns = [
    path("", views.statement, name="payments"),
    #    path("test-payment", views.test_payment, name="test_payment"),
    path("stripe-webhook", core.stripe_webhook, name="stripe_webhook"),
    path(
        "create-payment-intent", core.stripe_manual_payment_intent, name="paymentintent"
    ),
    path(
        "create-payment-superintent",
        core.stripe_auto_payment_intent,
        name="paymentsuperintent",
    ),
    path("stripe-pending", views.stripe_pending, name="stripe_pending"),
    path(
        "admin-payments-static",
        views.admin_payments_static,
        name="admin_payments_static",
    ),
    path(
        "admin-payments-static-history",
        views.admin_payments_static_history,
        name="admin_payments_static_history",
    ),
    path(
        "admin-payments-static-org-override",
        views.admin_payments_static_org_override,
        name="admin_payments_static_org_override",
    ),
    path(
        "admin-payments-static-org-override-add",
        views.admin_payments_static_org_override_add,
        name="admin_payments_static_org_override_add",
    ),
    path(
        "admin-payments-static-org-override-delete/<int:item_id>",
        views.admin_payments_static_org_override_delete,
        name="admin_payments_static_org_override_delete",
    ),
    path(
        "admin-view-stripe-transactions",
        views.admin_view_stripe_transactions,
        name="admin_view_stripe_transactions",
    ),
    path(
        "admin-view-stripe-transaction-detail/<int:stripe_transaction_id>",
        views.admin_view_stripe_transaction_detail,
        name="admin_view_stripe_transaction_detail",
    ),
    path("statement", views.statement, name="statement"),
    path("settlement", views.settlement, name="settlement"),
    path(
        "manual-adjust-member", views.manual_adjust_member, name="manual_adjust_member"
    ),
    path("manual-adjust-org", views.manual_adjust_org, name="manual_adjust_org"),
    path(
        "statement-admin-view/<int:member_id>",
        views.statement_admin_view,
        name="statement_admin_view",
    ),
    path("statement-csv", views.statement_csv, name="statement_csv"),
    path("statement-csv/<int:member_id>", views.statement_csv, name="statement_csv"),
    path("statement-pdf", views.statement_pdf, name="statement_pdf"),
    path("setup-autotopup", views.setup_autotopup, name="setup_autotopup"),
    path("update-auto-amount", views.update_auto_amount, name="update_auto_amount"),
    path(
        "admin-orgs-with-balance",
        views.admin_orgs_with_balance,
        name="admin_orgs_with_balance",
    ),
    path(
        "admin-members-with-balance",
        views.admin_members_with_balance,
        name="admin_members_with_balance",
    ),
    path(
        "admin-members-with-balance-csv",
        views.admin_members_with_balance_csv,
        name="admin_members_with_balance_csv",
    ),
    path(
        "admin-orgs-with-balance-csv",
        views.admin_orgs_with_balance_csv,
        name="admin_orgs_with_balance_csv",
    ),
    path(
        "admin-view-manual-adjustments",
        views.admin_view_manual_adjustments,
        name="admin_view_manual_adjustments",
    ),
    path("member-transfer", views.member_transfer, name="member_transfer"),
    path("manual-topup", views.manual_topup, name="manual_topup"),
    path("cancel-autotopup", views.cancel_auto_top_up, name="cancel_autotopup"),
    path(
        "statement-admin-summary",
        views.statement_admin_summary,
        name="statement_admin_summary",
    ),
    path("statement-org/<int:org_id>/", views.statement_org, name="statement_org"),
    path(
        "statement-csv-org/<int:org_id>/",
        views.statement_csv_org,
        name="statement_csv_org",
    ),
    path(
        "stripe-webpage-confirm/<int:stripe_id>/",
        views.stripe_webpage_confirm,
        name="stripe_webpage_confirm",
    ),
    path(
        "stripe-autotopup-confirm",
        views.stripe_autotopup_confirm,
        name="stripe_autotopup_confirm",
    ),
    path(
        "stripe-autotopup-off", views.stripe_autotopup_off, name="stripe_autotopup_off"
    ),
    path(
        "statement-org-summary/<int:org_id>/<str:range>",
        views.statement_org_summary_ajax,
        name="statement_org_summary_ajax",
    ),
    path(
        "member-transfer-org/<int:org_id>",
        views.member_transfer_org,
        name="member_transfer_org",
    ),
]
