from organisations.decorators import check_club_menu_access
from rbac.core import rbac_user_has_role
from rbac.views import rbac_forbidden

#
# @check_club_menu_access()
# def ad_hoc_manual_payments_htmx(request, club):
#     """ This could go in payments, orgs or club_sessions. Not sure which is best.
#
#     This handles one-off charges to a user
#
#     It can be part of a session or just a one off on its own
#     """
#
#     # Check user access. Allow directors or people with payments edit to do this
#     if not rbac_user_has_role(request.user, f"club_sessions.sessions.{club.id}.edit") and not rbac_user_has_role(request.user, f"payments.manage.{club.id}.edit"):
#         return rbac_forbidden(request, f"club_sessions.sessions.{club.id}.edit")
#
#
