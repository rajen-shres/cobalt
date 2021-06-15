.. _notifications-overview:


.. image:: images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

Notifications Overview
======================

Notifications is the communication centre of Cobalt. It is how all other modules
communicate with members and is also a notice board for events (actions, not
bridge events) that members may want to subscribe to be notified about.

There are many events that a Cobalt user may wish to be notified about.
For example, they may want to hear when a new post is added to a particular
forum, or when someone replies to a comment that they have made in a forum.
They may wish to be notified when the results become available for an event
they have played in, or when a congress in their area is announced.

A user may have different preferences for how they are notified as well.
One user may want SMS, another email and yet another may only wish to find
out when they visit the website. Of course, some users may not want to be
notified at all and others will want a combination of methods depending upon
what it is they are being notified about.

Notification Types
==================

There are five broad categories of notification:

System Broadcasts (*Not yet implemented*)
  Users will receive these regardless of preference. These are rare.
Broadcasts (*Not yet implemented*)
  These are typically emails from the National Body, Clubs, State
  Bodies etc. Users may opt out of these through their settings.
Named Specific (*Not yet implemented*)
   The calling module will provide a list of names. Users can
   choose how they are notified or choose to opt out. For example, Results tells
   Notifications that the results for an event are available and who played in the
   event. Notifications passes this information on to the member (or not, if the
   member opts out).
Happenings
  These are things that members choose to listen to. For example,
  a new Forum post.
Personal
  These are messages intended for a single recipient.

Notification Methods
====================

- **In App Notifications** - these are always provided. The user will see this when
  they log in to Cobalt.
- **Email** - HTML format emails.
- **SMS** - Short messages, often with links to pages within Cobalt.

User Experience
===============

Users always see notifications on the top right hand of the screen. They can
acknowledge a notification by clicking on them. Notifications should come with a
link that takes the user to the right relative URL for more information.

In addition to the In App Notification, users can also receive notifications
over email or SMS.

Creating Immediate Notifications
================================

You can create a notification for a user directly by calling
:func:`notifications.views.contact_member`. You need to provide the member,
message and type (SMS or Email) as a minimum.

This is the recommended way of communicating
with a member if you want standard notifications as this will also create
an internal notification message.

If you don't want the internal notification then you can call the sending
functions directly.

* :func:`notifications.cviews.send_cobalt_email` - sends an email.
* :func:`notifications.cviews.send_cobalt_sms` - sends an sms.

It is recommended that you do this rather than sending messages directly
so we can have a single point to maintain.

Creating User Listens
=====================

Sometimes you don't want to immediately notify a user but you do want to
set them up for later notifications. For example, if a user posts an
article in a Forum, they may want to be notified when someone comments on it.

In this case you should call :func:`notifications.views.create_user_notification`.

This will set up a rule to listen for the events that you request. If you no
longer want this (for example, if the post is deleted), then you should call
:func:`notifications.views.delete_user_notification`.

Event Types
-----------

The applications control their own event types, but the format of the string
used to identify them should follow a standard:

<application>.<function>.<action>

If necessary more levels can be added.

For example:

* forums.post.comment.new - *a comment has been added to a post*
* forums.post.delete - *a post has been deleted*

Notification of Events
======================

When something has happened in an application that a user **could** be
interested in, then notifications should be informed. It is better to
over communicate than to under communicate, but always expect to also have
to update the code within notifications as it isn't magic.

To announce an event has occurred call
:func:`notifications.views.notify_happening`.

This is the point at which if a member has registered to find out about
an event, then they will be notified.

Email
=====

The email set up is not trivial and worth understanding before you
dive into the code. We use a queue and send approach to email.
This is to address a few technical issues which are also worth
understanding, not just to see why this soultion was required but
also in case the situation changes or someone else has a better idea
of how to address this.

Usage
-----

The rest of this section explains why and how things work. If you
just want to send emails you can do the following::

    # Send single email
    from notifications.views import send_cobalt_email

    send_cobalt_email("a@b.com", "Subject", "Body")
    # Or
    send_cobalt_email("a@b.com, "Subject", "Body", member=user, reply_to="b@c.com")


    # Send a bunch of different messages
    from notifications.views import CobaltEmail

    email_sender = CobaltEmail()
    email_sender.queue_email("a@b.com", "Subject", "<h1>Hello</h1>")
    email_sender.queue_email("b@c.com", "Welcome", "<h1>Hi</h1>")
    email_sender.send()


    # Send one message to a bunch of people
    from notifications.views import send_cobalt_bulk_email
    send_cobalt_bulk_email(
        bcc_addresses=['a@b.com', 'b@c.com'],
        subject="Subject",
        message="<h1>Hello</h1>",
        reply_to="me@d.com",
    )

Requirements
------------

We need to be able to send a lot of the same emails to a group of
people (e.g. newsletters), and we also need to be able to send customised emails to
potentially large groups of people (e.g. statements).

Problems and Attempted Solutions
--------------------------------

The initial approach was just to send single emails in a loop.
This worked fine for most of the time, but occasionally the SMTP
server is slow to respond and the the user is faced with a hung
screen or a timeout.

The next approach was to start a thread to send the email and to
return immediately to the user. This works fine until a large
number of concurrent messages are sent and then we hit some sort
of thread limit on the server and emails do not get sent. This
one thread to one email approach was never going to be scalable.

For bulk emails, we greatly reduce the number of emails sent by
using the BCC field. Again, there is a limit here which depends upon
the SMTP provider but AWS limit it to 50 so we can send out our email
multiple times to 50 people at a time until it is sent. This uses
the function send_cobalt_bulk_email. This has one thread per
bulk email request which is scalable as they are rare. However,
this doesn't work at all for custom emails.

One further problem with using threads is that if Django is
restarted I do not believe that it will wait for these threads
to finish (very hard to test though). So we have the possibility that
a big mail out is happening at the time of a restart and the
emails do not get sent. We won't lose them, but they will sit in
the email table with a status of "Queued".

Current Solution
----------------

We use the send_cobalt_bulk_email solution described above for
genuine mass emails which are not customised.

For other use cases we have a queue and send approach. This moves
some of the logic back to the calling modules, but not very much.

To use it, do the following::

    from notifications.views import CobaltEmail

    email_sender = CobaltEmail()
    email_sender.queue_email("a@b.com", "Subject", "<h1>Hello</h1>")
    email_sender.queue_email("b@c.com", "Welcome", "<h1>Hi</h1>")
    email_sender.send()

How It Works
------------

Queuing an email will write it to the email table with a status of
"Queued".

Sending it will start a new thread (immediate return to the calling
program) which checks if the maximum number of allowed concurrent
email threads has been reached and if not it will start another one.

We also follow up with a cron job that calls a management function
to check for any stale messages and send them. In the event of the
threads being used up, the cronjob will ensure that the emails
are still send after a little delay.

At start up, the notifications module clears any recorded email
threads that are in the EmailThread table, in case they are left
behind from an interrupted restart (see notifications/apps.py).

We should never get a thread left in the list after it has finished
because the try: finally: block in the send code ensures that
even there are logic errors, the entry will be deleted (but you
never know!).