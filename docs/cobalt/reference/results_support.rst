:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../../images/results.jpg
 :width: 200
 :alt: Results

==========================================
Supporting the Results Application (edit)
==========================================

*This page describes the internal workings of this application and is intended to
help you if you need to support the code.*

Results uses the `USEBIO file format <https://www.usebio.org/>`_.

Results uses Thomas Andrews' Deal via Antony Lee's Python wrapper https://github.com/anntzer/redeal

This relies on an installed binary which must match the operating system that Cobalt is
running on. Binaries live in `utils/bin`, at the time of writing on Mac binaries can be found here.

The Deal package comes with the required Linux binaries, however you may need to
build one for your environment (see below). The code is written in C.

Building the Binaries
=====================

If you ever need to build the binaries from scratch, this will hopefully help.

From the command line of a suitable directory, run these commands:

.. code-block:: bash

    git init
    git remote add origin https://github.com/dds-bridge/dds.git
    git pull origin develop
    cd src

    # Copy an appropriate make file. e.g.
    cp Makefiles/Makefile_Mac_gcc_shared Makefile

Now edit `Makefile` to make the following changes:

- comment out boost at the top
- change compiler to gcc

Change the options that make complains about:

- remove -fno-use-linker-plugin
- remove -fopenmp
- remove -Wlogical-op
- remove -Wnoexcept
- remove -Wstrict-null-sentinel
- change -Wno-write-string to -Wno-write-strings

On Intel chips for Mac you also needed to remove -Wsign-conversion

.. code-block:: bash

    make clean
    make
    # Copy file into your Python environment, e.g.
    cp libdds.so /my_venv/lib/python3.7/site-packages/ddstable/libdds.so
    # For non-virtual environments perhaps
    sudo cp libdds.so /usr/local/lib/libdds.so

Performance
===========

The Results application calculates the double dummy makable contracts when a user requests
to view a hand. If this becomes a performance bottleneck then this step could be moved to
the file upload process and the double dummy analysis stored in the database.