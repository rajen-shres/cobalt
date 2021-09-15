.. _forums-overview:


.. image:: images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

=====================
Django for Pork Chops
=====================

This assumes you know Python,
if you don't then you should first read :doc:`python_for_porkchops`.

************
Introduction
************

It takes about two years to become proficient in Django, some people
are quicker and some are slower. This document is intended to try to
help people to get there quicker.

As someone wise once said (possibly Eleanor Roosevelt),
you should try to learn from other's mistakes
as there isn't time to make them all yourself. Here are some snippets to
get you going.

First Steps
===========

If you haven't used Django before then your best bet is a Youtube video series,
a tutorial or a paid course. There are lots to choose from. Be aware that you
will never use half of the stuff that they try to teach you. No real Django
developer knows the commands to create a project from scratch or to add an
application to an existing project, it doesn't happen often enough for you to
need to memorise it and it can be looked up easily. What they do know is that
both of these things are possible, and so will you when you finish your training.

There are really only a few key concepts that you need to understand to get
started.

Models, Views, Forms and Templates (oh, and URLs but nobody ever mentions them, and Template Tags whatever they are)
====================================================================================================================

*Skip this is you know Django, this is for people too lazy to do a course.*

If you have done a Django course or even just googled Django to see what it is,
you will know that Django is based upon a model-template-views (MTV) architecture.
This makes it sound a lot like the popular model-view-controller (MVC) architecture
which makes people feel good.
Even `Wikipedia <https://en.wikipedia.org/wiki/Django_(web_framework)>`_ believes this.

Unfortunately, that is totally wrong. Marketing people love putting three words
together, it works really well with triggering things in humans. Ready, Steady, Go!
Veni, Vidi, Vici. You get the idea. The problem is that Django actually has six
parts to it, and making people think it has three might be good for rousing interest
but is likely a big cause of the problems with people writing code in the wrong place.

So first up forget that "I want my... MTV" nonsense and realise that Django has six components that
do very different things. When you are in your IDE typing letters and numbers into
one of these six files, make sure what you are typing relates to what the file is supposed
to do.

* **URLs** - Maps a URL to a view. Very boring.
* **Models** - Data
* **Forms** - Validation and some pre-filling of values
* **Views** - Business logic. Code to run before you format things
* **Templates** - Presentation. This is where you wrap your data and forms in HTML for the browser
* **Template Tags** - Presentation logic. Code to run while you format things

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

However, Django lives in the real world where things can get a bit uglier. It isn't always possible (or desirable)
for all of our code to run in views **before** we call our templates to make things pretty. Sometimes we need to
do something as we go through the template. Django's template system is pluggable so you can swap it out for another
one if you like. I wouldn't bother, the default is fine, but it is pretty simple. If you want to do anything complicated
then you should generally try to do it in your view before you call the template. If your view code is ending up full of
nasty HTML strings though then you should consider moving that all into template tags. These are just Python code but
you can call them from the template after you have provided the data from the view. HTML code in your nice clean view
which is handling the business logic just looks wrong. Lift up the carpet and sweep all that ugly code away into a
template tag, then for 99% of the time you can pretend it doesn't exist and your views can carry on focussing on
what they do best, handling business logic.

The only other part of Django that you will deal with regularly is **settings.py** but the tutorials cover this
fairly well. Environment variables are definitely your friend here, although other ways to manage different
settings between production and non-production environments are possible.

That's the end of the beginners bit, if you haven't done so already go and learn Django.

***********
Information
***********

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

*******
Journey
*******

Let us set some markers for you to track your journey as a Django developer. See how far you
have come already and what things might be next.

Level 1 - Basic Explorer
========================

You can write Django that works. You have got the hang of views and templates. You have
probably written three things in three different ways but you are getting there. Somethings
confuse you and it takes a long time to work things out, but you get there in the end.

Level 2 - Quietly Confident
===========================

You have started to really understand models. You can do use foreign keys to get data
that you used to have to do in two separate queries. You don't have to look up the common
template tags any more. You have discovered Crispy Forms and spent quite a long time
getting them to do what you want. You think you know how static works now but you still
aren't sure which of the static directories is which.

Level 3 - Clunky Builder
========================

You swear you will never use Crispy Forms again and you build your own HTML forms.
You have discovered 'include' and 'extends' and your templates are looking nicer.
You have played with something else really cool, maybe writing your own template tags
or overriding save() in models, but you can't remember where you put it.

Level 4 - Baby Guru
===================

You found a bunch of Django add-ons including the debug toolbar and it showed how poor
some of your database queries are. You now know what an N+1 problem is and you
have started getting your head around pre-fetch and fetch-related. You have finally started
writing some tests.

**********
Principles
**********

Django, and Python for that matter, is heavy on principles. You will hear people talking about DRY and
being Pythonic, which probably makes you want to reach for a sick bag. Tim Peters came up with 20 aphorisms (yup,
maybe get a bucket this time) for Python, called the `The Zen of Python <https://www.python.org/dev/peps/pep-0020/>`_
(make it is a large bucket). This is even given the honour of being a Python Enhancement Proposal (PEP) and
is hidden in the source code as an Easter Egg. I think
he was on his second bottle of Midori when he wrote these though as all but one of them are complete nonsense.
He also only wrote down 19 presumably beacuse when you finally attain enlightenment as a Python programmer the 20th
one will be self evident. Or more likely it was even worse than "Although that way may not be obvious at
first unless you're Dutch.".

Django nerds also like to talk about DRY (Don't Repeat Yourself) as if it was something new. You'll work this out entirely
on your own after you have to update very similar code in four different places and decide to create a common function for
it.

Useful Ones
===========

Okay, so which principles are actually useful here.

Do What Django Wants
--------------------

You are using the Django framework so do things the Django way even if you don't like it. Consistency is much more
important than anything else when maintaining code so if you stick to how Django was designed you won't go far wrong.
Django says - Database stuff goes in Models, Business logic goes in Views, Validation goes in Forms
and Presentation stuff goes in Templates.
If you find yourself writing presentation stuff in a form (I'm looking at you Crispy Forms) then you are making a mistake.

Explicit is Better than Implicit
--------------------------------

This is the one that Tim Peters got right. All it means is don't hide stuff that will be hard for others to find.
For example, when you start writing your own template tags and using them everywhere, you will be tempted to add them
to context_processors instead of having to load them in every template. Now you find the exception where you don't want
to load it in a template. Maybe there is a name clash with another set of template tags that you want to use. Good luck
finding how it got loaded. Your code won't run any faster for loading the template tags in a different place (slower
for all of the times you don't use them).

You could always put a comment at the top of your templates to tell the poor person who comes along to support it
that this template uses template tags from my_tags. The clever people who brought you Django actually have a shorthand
notation for this comment::

    {% load my_tags %}

Signals are another good way to obscure your code. So is overriding methods unless you use them in a lot of places.
Here is a simple example. You have a model with a CharField defined that has a max_length of 20. You hit a problem
when something longer than 20 gets put into the field. You could make it bigger or change it to a TextField (infinite
length but same properties) but you aren't sure of the consequences so instead you do this::

    my_thing.short_field = random_value[:20]
    my_thing.save()

Now it works fine. But what if this happens somewhere else? You could look for all instances of random_value and
do this to them all, but that is ugly and someone else might add a new one and forget to do it. What about just
overriding the save() method on the model for my_thing? Now you are only making the change in one place and your code
is far simpler::

    my_thing.short_field = random_value
    my_thing.save()

    def save():
        self.short_field = self.short_field[:20]

Nice solution! Except six months later you are trying to work out why data in short_field is getting truncated.
The system throws no errors and the code looks fine. When you examine the variables they have the long value but
later it has been truncated. This could take you a very long time to solve.

Tim Peters has two others that are pretty much okay, he actually split one thing into two in his late night
effort to get to 20: "Errors should never pass silently." and "Unless explicitly silenced.". That is pretty
much the same thing as here though, nice try Tim.

Write Comments
--------------

There are a bunch of dangerous idiots going around preaching that comments are the work of the devil and finding
comments in code is a sure sign that the code is bad, otherwise why would you need to write comments? Use better
variable names, refactor the code to be easier to read, delete the comments. These people are insane, ignore them.
Here is a much better philosophy - instead of thinking that the comments are there to explain the code to humans,
try thinking that the code is only there because the computer can't read the comments.

Apart from showing your most beautiful work to people at parties there are only three reasons to be looking at code:

#. It's broken and you need to fix it
#. It works but you need it to do something else now
#. You want to understand what it does and how (to copy it or to use it)

Every one of these is going to be easier if the code has comments, especially the first one which is the worst
reason to be looking at code (second worst, you could be at a party and someone is showing it to you).

Take this example::

    # Save original value
    original_value = request.POST.get("my_value")

    # Loop through and create list of options
    for item in items:
        my_list.append(item)

    # add the original value back into our list
    my_list.append(item)

It is very obvious that the last line of code doesn't do what its comment says it is going to do.

There are lots of excuses for writing bad code (short of time, hate my job, drunk, stupid) but no excuse for not
writing comments.

###########
Refactoring
###########

This has nothing really to do with Django but neither did the last point about comments and you didn't notice until
I just pointed it out.

Refactoring is the most fun you can have in programming without being able to tell anyone you did it.
Ignoring the obvious parallels, there is nothing better than taking some badly structured code and
turning it into something beautiful and easy to maintain.

Principles - DRY, refactor the 3rd time, comments, explicit over implicit

Forms



Tests

Tools

Common commands, black flake8

Browse libarires to see what they do

Structure - refactor

Signals

CBVs

Production and Other Environments

