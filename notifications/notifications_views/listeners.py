from notifications.models import NotificationMapping
from notifications.notifications_views.core import (
    add_in_app_notification,
    send_cobalt_email_preformatted,
    send_cobalt_email_with_template,
)


def notify_happening_forums(
    application_name,
    event_type,
    msg,
    context,
    topic,
    subtopic=None,
    link=None,
    user=None,
):
    """sub function for notify_happening() - handles Forum events
    Might be able to make this generic
    """
    listeners = NotificationMapping.objects.filter(
        application=application_name,
        event_type=event_type,
        topic=topic,
        subtopic=subtopic,
    )

    for listener in listeners:

        # Don't send to person who triggered this to happen
        if user != listener.member:

            # Add name to context
            context["name"] = listener.member.first_name

            # Send email
            send_cobalt_email_with_template(
                to_address=listener.member.email, context=context
            )

            # Add link
            add_in_app_notification(listener.member, msg, link)


def notify_happening(
    application_name,
    event_type,
    msg,
    context,
    topic,
    subtopic=None,
    link=None,
    user=None,
):
    """Called by Cobalt applications to tell notify they have done something.

    Main entry point for home notifications of events within the system.
    Applications publish an event through this call and Notifications tells
    any member who has registered an interest in this event.

    Args:
        context (dict): variables to pass to the template. See the comments on send_cobalt_email_with_template for more
        user(User): user who triggered this event, they won't be notified even if they are a listener
        application_name(str): name of the calling app
        event_type(str): what event just happened
        topic(str): specific to the application, high level event
        subtopic(str): specific to the application, next level event
        msg(str): a brief description of the event
        link(str): an HTML relative link to the event (Optional)

    Returns:
        Nothing

    """

    if application_name == "Forums":
        notify_happening_forums(
            application_name=application_name,
            event_type=event_type,
            msg=msg,
            context=context,
            topic=topic,
            subtopic=subtopic,
            link=link,
            user=user,
        )


def add_listener(
    member,
    application,
    event_type,
    topic=None,
    subtopic=None,
    notification_type="Email",
):
    """Add a user to be notified of an event"""

    listener = NotificationMapping(
        member=member,
        application=application,
        event_type=event_type,
        topic=topic,
        subtopic=subtopic,
        notification_type=notification_type,
    )
    listener.save()


def remove_listener(member, application, event_type, topic=None, subtopic=None):
    """Remove a user from being notified of an event"""

    listeners = NotificationMapping.objects.filter(
        member=member,
        application=application,
        event_type=event_type,
        topic=topic,
        subtopic=subtopic,
    )
    for listener in listeners:
        listener.delete()


def check_listener(member, application, event_type, topic=None, subtopic=None):
    """Check if a user is being notified of an event"""

    listeners = NotificationMapping.objects.filter(
        member=member,
        application=application,
        event_type=event_type,
        topic=topic,
        subtopic=subtopic,
    )
    if listeners:
        return True
    else:
        return False


def create_user_notification(
    member,
    application_name,
    event_type,
    topic,
    subtopic=None,
    notification_type="Email",
):
    """create a notification record for a user

    Used to programmatically create a notification record. For example Forums
    will call this to register a notification for comments on a users post.

    Args:
        member(User): standard User object
        application_name(str): name of the Cobalt application to follow
        event_type(str): event e.g. forums.post.create
        topic(str): specific to the application. e.g. 5 to follow forum with pk=5
        subtopic(str): application specific (optional)
        notification_type(str): email or SMS

    Returns:
        Nothing
    """

    notification = NotificationMapping()
    notification.member = member
    notification.application = application_name
    notification.event_type = event_type
    notification.topic = topic
    notification.subtopic = subtopic
    notification.notification_type = notification_type
    notification.save()
