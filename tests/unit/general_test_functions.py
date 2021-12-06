from django.db.models import TextField, CharField


def test_model_instance_is_safe(manager, model_instance, exclude_list=[]):
    """Test bleach security on text and char fields. The save method of these fields should use Bleach to
    sanitise the data. We save it to see if this works.

    Args:
        manager: CobaltTestManagerIntegration
        model_instance: An instance of a model to test
        exclude_list: list of strings. Names of fields to exclude from the testing. We whitelist not blacklist
    """

    model_type = model_instance._meta.model.__name__

    # Get all of the fields on model_instance
    for model_field in model_instance._meta.fields:

        # Skip if in exclude list
        if model_field.name in exclude_list:
            continue

        # only test long char and text fields
        if type(model_field) == TextField or (
            type(model_field) == CharField and model_field.max_length >= 27
        ):

            # set value to something dodgy
            setattr(model_instance, model_field.name, "<script>alert('h')</script>")

            # save it
            model_instance.save()

            # Get the data back
            new_value = getattr(model_instance, model_field.name)

            ok = new_value == "alert('h')"
            manager.save_results(
                status=ok,
                test_name=f"Check Bleach prevents scripts -{model_type}.{model_field.name}",
                test_description=f"Add some unsafe code to the {model_field.name} field of {model_type} "
                f"and check that it does not get saved. Bleach should filter it out.",
                output=f"Expected code to be removed. Status={ok}. Field returned as '{new_value}'.",
            )
