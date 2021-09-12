.. _forums-overview:


.. image:: images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

Django for Pork Chops
=====================

This assumes you know Python,
if you don't then you should first read :doc:`python_for_porkchops`.

Introduction
------------

It takes about two years to become proficient in Django, some people
are quicker and some are slower. This document is intended to try to
help people to get there quicker.

As someone wise once said, you should try to learn from other's mistakes
as there isn't time to make them all yourself. Here are some snippets to
get you going.

First Steps
-----------

If you haven't used Django before then your best bet is a Youtube video series,
a tutorial or a paid course. There are lots to choose from. Be aware that you
will never use half of the stuff that they try to teach you. No real Django
developer knows the commands to create a project from scratch or to add an
application to an existing project, it doesn't happen often enough for you to
need to memorise it and it can be looked up easily. What they do know is that
both of these things are possible, and so will you when you finish your training.

There are really only a few key concepts that you need to understand to get
started.

Models, Views and Templates (oh, and URLs but nobody ever mentions them)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

*Skip this is you know Django, this is for people too lazy to do a course.*

You probably wouldn't be using Django if you didn't want to store data
in a database. Use Postgres unless you have to use something else and
don't worry, you'll almost never have to touch it, Django does all of that
for you.

The way into the database is through a Model. Let's assume you have created
your Django project and called it inventory and you have added an application
called warehouse. If you look in the directory inventory/warehouse you will
find a file called models.py, and this is where you're database definitions
will go.

A class represents a table and an attribute of the class represents a column::

    class ClubLog(models.Model):
        """log of things that happen for a Club"""

        organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
        actor = models.ForeignKey(User, on_delete=models.CASCADE)
        action_date = models.DateTimeField(auto_now_add=True)
        action = models.TextField("Action")

So this creates a table ClubLog (in the database it will be club_log) and
four columns. If you have come across foreign keys before in databases you
probably hate them. They are really fiddly to work with. However, Django
takes care of all of that for you and they work brilliantly so use them
as much as possible to define the linkages between your data.

You don't need to access the database directly, you can let Django do
all of that for you. It is very good at optimising queries if you give it
a chance. If I wanted to get some data from the table above I could do
this::

    logs = ClubLog.objects.filter(action="My Data")
    for log in logs:
        print(log.organisation)

There are loads of really clever things that you can do with Django to
handle your data, but that is enough for now.

Okay, so that is the database part, you still want to be able to write your
business logic and to present your data.

Django is a web framework so while it can be used for other things, it is
mostly designed for serving web pages. Web pages are transactional, the user
provides where they want to go (the URL) and optionally some data (usually
GET or POST data) that goes with it. The server processes the data and usually
shows the user a web page.

Models.py has our database definitions, then we have views.py which holds our
code and urls.py which has our URLs. Urls.py is pretty simple, all it does is point
a url (e.g. /warehouse/list-contents) to a chunk of code and optionally handle some
parameters if we have them (e.g. /warehouse/show_details/stock-item-365). You will
hate all of the time that you spend in urls.py and hopefully a future version of
Django will get rid of this and maybe just put the definitions directly into
view.py.

So the user has told us what they want to do, urls.py has mapped that to a function
in views.py and now we can build our screen and show it to the user.

The function in views.py will do the business logic and then provide parameters to
a template to do the formatting. Something like this::

    # in views.py
    def show_details(request, stock_item_no):

        stock_item = StockItem.objects.get(pk=stock_item_no)

        return render(request, "warehouse/stock_item.html", {"stock_item": stock_item})

Then in the template we do something to format it::

    {# in stock_item.html #}
    <html>
        <body>
         <h1>{{ stock_item.name }}</h1>
         We have {{ stock_item.quantity }} available.
         </body>
    </html>

The template has it's own language as you can see.

And that's it. That's the basics of Django.

A couple more things to mention - the first parameter to our view function is *request*, which
has a bunch of possibly useful stuff in it. We didn't use it in this example but if this was
a POST then request.POST would have all of the data that the user provided. Speaking of the
user, if the user is logged in then request.user would tell us who they are.

You end up doing a lot of stuff with forms, so forms.py will make an appearance in your
directory before long. Forms can link directly to the Models and handle validation and
things more easily than writing everything in the view.

The other moving parts of Django that you will deal with regularly are:

* **settings.py** - variables to control things
* **context_processors.py** - global variables for templates
* **templates** - there is the whole templates language and includes and things to learn

That's the end of the beginners bit, if you haven't done so already go and learn Django.

Information
-----------

Syntax really doesn't matter. For example, as long as you remember there is a template tag that formats
numbers, you can easily Google it to find out the right word to use. What matters is design and patterns.

The internet is full of opinion pieces on how to do such-and-such in Django. There are also
millions of Stack Overflow questions, some of which are useful. The problem is that about 50%
of the content is wrong. Some of it is just out of date which is understandable. Often something that
needed a work around in version 1.8 has been fixed in 3.2. The answer will still be there though (on
Stack Overflow scroll down to the bottom and look for **Update**, this will often have a less
popular answer that is correct for the current version).

Why is so much content wrong? Often the videos and articles are written by people who have
never actually written a real Django application. Good Django developers get paid to write code,
they don't have time to make youtube videos about it. For that reason talks at conferences are
often much better than articles.

The other problem is that someone who is seen as an influencer says something stupid and
all the nodding heads copy it. The best thing is to only ever take what you find on the internet
as suggestions and to work out for yourself if they are good suggestions or not. I will go through
some of them here. Of course the same advice applies to this document.

Journey
-------

Let us set some markers for you to track your journey as a Django developer. See how far you
have come already and what things might be next.

Level 1 - Basic Explorer
^^^^^^^^^^^^^^^^^^^^^^^^

You can write Django that works. You have got the hang of views and templates. You have
probably written three things in three different ways but you are getting there. Somethings
confuse you and it takes a long time to work things out, but you get there in the end.

Level 2 - Quietly Confident
^^^^^^^^^^^^^^^^^^^^^^^^^^^

You have started to really understand models. You can do use foreign keys to get data
that you used to have to do in two separate queries. You don't have to look up the common
template tags any more. You have discovered Crispy Forms and spent quite a long time
getting them to do what you want. You think you know how static works now but you still
aren't sure which of the static directories is which.

Level 3 - Clunky Builder
^^^^^^^^^^^^^^^^^^^^^^^^

You swear you will never use Crispy Forms again and you build your own HTML forms.
You have discovered 'include' and 'extends' and your templates are looking nicer.
You have played with something else really cool, maybe writing your own template tags
or overriding save() in models, but you can't remember where you put it.

Level 4 - Baby Guru
^^^^^^^^^^^^^^^^^^^

You found a bunch of Django add-ons including the debug toolbar and it showed how poor
some of your database queries are. You now know what an N+1 problem is and you
have started getting your head around pre-fetch and fetch-related. You have finally started
writing some tests.

Principles - DRY, refactor the 3rd time, comments, explicit over implicit

Tests

Tools

Common commands, black flake8

Browse libarires to see what they do

Structure - refactor

Signals

CBVs


