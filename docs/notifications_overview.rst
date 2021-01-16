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
