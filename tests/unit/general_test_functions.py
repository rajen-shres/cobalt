from django.db.models import TextField, CharField
from django.test import Client


def test_model_instance_is_safe(manager, model_instance, exclude_list=[]):
    """Test bleach security on text and char fields. The save method of these fields should use Bleach to
    sanitise the data. We save it to see if this works.

    Args:
        manager: CobaltTestManagerIntegration
        model_instance: An instance of a model to test
        exclude_list: list of strings. Names of fields to exclude from the testing. We whitelist not blacklist
    """

    model_type = model_instance._meta.model.__name__
    success_count = 0
    skip_count = 0
    non_text_count = 0
    success_list = []

    # Get all of the fields on model_instance
    for model_field in model_instance._meta.fields:

        # Skip if in exclude list
        if model_field.name in exclude_list:
            skip_count += 1
            continue

        # only test long char and text fields
        if not (
            type(model_field) == TextField
            or (type(model_field) == CharField and model_field.max_length > 27)
        ):
            non_text_count += 1
            continue

        # set value to something dodgy
        setattr(model_instance, model_field.name, "<script>alert('h')</script>")

        # save it
        model_instance.save()

        # Get the data back
        new_value = getattr(model_instance, model_field.name)

        ok = new_value == "alert('h')"

        # Report errors now, report success as a summary
        if not ok:

            manager.save_results(
                status=ok,
                test_name=f"Check Bleach prevents scripts -{model_type}.{model_field.name}",
                test_description=f"Add some unsafe code to the {model_field.name} field of {model_type} "
                f"and check that it does not get saved. Bleach should filter it out.",
                output=f"Expected code to be removed. Status={ok}. Field returned as '{new_value}'.",
            )

        else:
            success_list.append(model_field.name)
            success_count += 1

    # Summary after loop is complete
    if success_list:
        manager.save_results(
            status=True,
            test_name=f"Check Bleach prevents scripts - SUMMARY -{model_type}",
            test_description=f"Add some unsafe code to the text fields of {model_type} "
            f"and check that it does not get saved. Bleach should filter it out. "
            f"This test is the summary of"
            f"successes.",
            output=f"Deliberately skipped: {skip_count}. Did not test non-text fields (or fields that "
            f"were too short): {non_text_count}. Passed {success_count}. Successful fields tested "
            f"were {success_list}",
        )


def get_django_client_object(user):
    """return a valid client object for a user"""

    client = Client()
    client.force_login(user)

    return client


def get_django_request_object(user):
    """return a valid request object for a user"""

    client = get_django_client_object(user)
    response = client.get("/")
    return response.wsgi_request
