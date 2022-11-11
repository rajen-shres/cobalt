:orphan:

.. image:: ../../images/cobalt.jpg
 :width: 300
 :alt: Cobalt Chemical Symbol

.. image:: ../../images/aws.png
 :width: 300
 :alt: Amazon Web Services

#######################
Backups Overview
#######################

This page relates only to the ABF production version of Cobalt.

*******
Backups
*******

Basic Backups
=============

We use AWS Relational Database Service (RDS) for our databases.
This is a fully managed service and handles the basic housekeeping
that we need to perform. Full backups (RDS calls them snapshots) are taken each day at about 2:30am.
They are retained for 14 days in production and 7 days for the other environments.

Snapshots can be taken manually, and it recommended that this happens for any major release.

Taking a snapshot prevents database updates at that time and can take time if the database is large.

Basic Restores
==============

You can restore a snapshot from the RDS management console. It will be given a new name and you will need
to point the associated Django Elastic Beanstalk environment at the new database in order to use it.

Additional Backups
==================

While it is unlikely that anything will go wrong with RDS itself, it is possible for other factors to
affect our database. For example, failure to pay the bill would result in the account being shutdown or
human error could cause the production database and all of its snapshots to be deleted when the intention was
to remove UAT.

For this reason we have an off-system backup which runs daily. This is not without risk as it needs to access
production data and systems in order to copy the data. It also requires maintenance and testing. The IT equivalent
of the medical joke "The operation was successful, but the patient died" is "The backups worked perfectly, it
was the restores that had problems." For that reason, as well as copying the data we also restore and test it
each time.

Unlike the RDS backups, our additional backups do not lock the database for writes, so they are "dirty" backups
and can suffer from integrity issues if the data changes in an inconsistent way while the backup is being taken.
Cobalt uses a lot of foreign keys and so it is likely that if data changes we will have problems. As an extreme example,
if a user registers with the system and posts a comment in a Forum while the backup is running, we could find that we
have a Forum comment that is made by a user who does not exist in the backup data set. **For this reason it is best
to avoid doing anything else while the additional backups run.**

How It Works
------------

The script ``utils/aws/copy_data_from_production.sh`` handles off-system backups. It requires an environment to
exist on another (development) machine outside of the AWS infrastructure. The instructions for setting this up are
contained as comments in the script itself.

This calls ``utils/aws/copy_data_from_production_dump.sh`` on the application server to do the actual database extract.

We use the Django command ``manage.py dumpdata`` to produce an database dump file and copy that to the development
machine where it is loaded into a prod_copy database for testing.

Back in the day, standard practice was for small offices to get the local manager to take a back up tape
home with them once a week. More recently it has been easier just to ask the NSA for a copy of your
data if you lose it. We have gone for a half way solution. The data is stored outside AWS but I'm not
telling you where.

