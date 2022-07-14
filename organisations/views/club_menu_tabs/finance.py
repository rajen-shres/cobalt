from django.shortcuts import get_object_or_404

from cobalt.settings import GLOBAL_CURRENCY_SYMBOL
from organisations.decorators import check_club_menu_access
from organisations.models import ClubLog
from organisations.views.club_menu import tab_finance_htmx
from payments.models import UserPendingPayment


@check_club_menu_access(check_payments=True)
def cancel_user_pending_debt_htmx(request, club):
    """Cancel a debt for a user"""

    user_pending_payment = get_object_or_404(
        UserPendingPayment, pk=request.POST.get("user_pending_payment_id")
    )
    if user_pending_payment.organisation != club:
        message = "This debt is not for this club"
    else:
        user_pending_payment.delete()
        message = "Pending payment deleted"

        ClubLog(
            organisation=club,
            actor=request.user,
            action=f"Cancelled debt for {user_pending_payment.system_number} for {GLOBAL_CURRENCY_SYMBOL}{user_pending_payment.amount:.2f}",
        ).save()

    return tab_finance_htmx(request, message=message)
