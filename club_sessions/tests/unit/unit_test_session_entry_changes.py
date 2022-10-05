from club_sessions.models import Session, SessionType, SessionEntry
from club_sessions.views.core import bridge_credits_for_club
from organisations.models import Organisation
from tests.test_manager import CobaltTestManagerIntegration


class SessionEntryChangesTests:
    """Unit tests Session Entry changes such as changing payment method, or fee"""

    def __init__(self, manager: CobaltTestManagerIntegration):
        self.manager = manager

    def bridge_credit_tests(self):
        """Tests for changes to bridge credits"""

        # load static
        club = Organisation.objects.filter(name="Payments Bridge Club").first()
        session_type = SessionType.objects.filter(organisation=club).first()
        bridge_credits = bridge_credits_for_club(club)

        # create a session
        session = Session(
            director=self.manager.alan,
            session_type=session_type,
            description="Testing session entries",
        )
        session.save()

        # create a session entry
        session_entry = SessionEntry(
            session=session,
            system_number=100,
            pair_team_number=1,
            seat="N",
            payment_method=bridge_credits,
            fee=20,
            is_paid=False,
        )
        session_entry.save()

        self.manager.save_results(
            status=True,
            test_name="Added session",
            test_description="Added session",
            output="Ok",
        )
