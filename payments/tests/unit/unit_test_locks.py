from threading import Thread

from django.db.transaction import atomic

from payments.models import MemberTransaction
from payments.views.core import update_account
from tests.test_manager import CobaltTestManagerUnit
from utils.models import Lock


def _helper_thread_function(i, user):
    """helper to run in multiple threads"""

    update_account(
        member=user,
        amount=10.0,
        description="Cash",
        payment_type="Refund",
        debug=f"{i}",
    )


class AccountUpdateTests:
    """Unit tests for the account update function. These test multiple simultaneous updates"""

    def __init__(self, manager: CobaltTestManagerUnit):
        self.manager = manager

    def account_update(self):
        """Tests for the account update"""

        new_lock = Lock(topic="Account Update Lock")
        new_lock.save()
        print(f"Lock set up - {new_lock}")
        del new_lock

        print("Setting initial value")

        # set initial balance
        update_account(
            debug="initial",
            member=self.manager.natalie,
            amount=10.0,
            description="Initial",
            payment_type="Refund",
        )

        print("Finished initial value")

        print("Seeing if lock is in DB")

        lock3 = Lock.objects.all()
        print(lock3)

        # Run a bunch of threads concurrently

        threads = []

        for i in range(10):
            this_thread = Thread(
                target=_helper_thread_function, args=[i, self.manager.natalie]
            )
            threads.append(this_thread)

        # Start all threads
        for this_thread in threads:
            this_thread.start()

        # Wait for all of them to finish
        for this_thread in threads:
            this_thread.join()

        # Check results
        results = MemberTransaction.objects.filter(
            member=self.manager.natalie
        ).order_by("pk")

        expected_balance = 10
        errors = []
        for result in results:
            if result.balance != expected_balance:
                errors.append(f"Expected {expected_balance}, got {result.balance}")
            expected_balance += 10

        self.manager.save_results(
            status=not errors,
            test_name="Multiple concurrent calls to update_account",
            test_description="Run multiple thread to update the account for Natalie. Should be processed in order.",
            output=f"Errors found: {errors}",
        )

        print("Locks in db after")
        lock3 = Lock.objects.all()
        print(lock3)
