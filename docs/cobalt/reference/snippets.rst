:orphan:

###########################################
Snippets
###########################################

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../../images/snippet.jpg
 :width: 300
 :alt: Snippet

.. note:: This page contains things that are useful shortcuts for developers.

.. contents:: On This Page
   :depth: 2
   :local:
   :backlinks: none

Sphinx
======

References
----------

- `RST Cheatsheet <https://bashtage.github.io/sphinx-material/rst-cheatsheet/rst-cheatsheet.html>`_

Code
----

To display code you can use, the shorthand double colon::

    Here is some code::

        def func():
            return

The default code type is Python, but you can specify other types of code::

    .. code-block:: shell

       #!/bin/sh
       echo "Hello"

Headings
--------

* # with overline, for parts
* \* with overline, for chapters
* =, for sections
* -, for subsections
* ^, for subsubsections
* ", for paragraphs

Links
-----

External links::

    `Link text <https://domain.invalid/>`_

Internal links::

    .. _my-reference-label:

    Section to cross-reference
    --------------------------

    Link to this with :ref:`my-reference-label`.

