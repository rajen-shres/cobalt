import pytest

from accounts.models import User


@pytest.mark.django_db
def test_my_thing():
    user = User.objects.filter(system_number=620246).first()

    assert user.first_name == "Mark"
