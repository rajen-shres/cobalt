:orphan:

.. image:: ../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../images/api.jpg
 :width: 300
 :alt: API

=================
API Overview
=================

Cobalt uses `Django Ninja <https://django-ninja.rest-framework.com/>`_ for its Application
Programming Interface (API). We don't use Django Rest Framework despite it being more popular
simply because Django Ninja is better. It is fast, secure and very easy to use. Even if you
haven't used it before, you should find it very easy. The format is similar to Flask.

All of the authentication is handled by `api/urls.py`.

All of the router definitions (/api/something) can be found in `api/apis.py`.

You can test the APIs by going to `/api/docs`.

All APIs should end with a version number, eg. /api/do-something/v4.5. The API call and the version
are logged automatically so we know who is using it.

Usage
=====

Windows Example
---------------

You can use a batch file to access the APIs, for example::

    @echo off
    cd "\AJ SMS\"
    for %%a in (*) do curl -X "POST" https://test.myabf.com.au/api/cobalt/sms-file-upload/v1.0 -H "accept: */*" -H "key: test_RPbRG7MH2j()UiLfaHNEOZGSprybGMzG^rh" -H "Content-Type: multipart/form-data" -F "file=@%%a;type=text/plain"
    move *.* archive
    exit

