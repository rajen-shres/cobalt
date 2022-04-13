#!/bin/bash

# commands to run after each deployment
# These MUST be re-runnable (not fail or create duplicates if run again)

. /var/app/venv/staging-LQM1lest/bin/activate

cp /var/app/current/cobalt/static/copy-to-media/pic_folder/* /cobalt-media/pic_folder/
mkdir /cobalt-media/email_banners/
cp /var/app/current/cobalt/static/copy-to-media/email_banners/default_banner.jpg /cobalt-media/email_banners/

./manage.py migrate
./manage.py createsu
./manage.py create_abf
./manage.py add_rbac_static_forums
./manage.py add_rbac_static_payments
./manage.py add_rbac_static_orgs
./manage.py update_club_rbac_groups
./manage.py add_rbac_static_events
./manage.py add_rbac_static_notifications
./manage.py add_rbac_static_support
./manage.py add_rbac_static_club_sessions
./manage.py create_states
./manage.py add_superadmin
./manage.py add_notifications_templates

# Replace cron
crontab utils/cron/crontab.txt
