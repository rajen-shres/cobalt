#!/bin/sh

./manage.py migrate
./manage.py createsu
./manage.py create_abf
./manage.py add_rbac_static_global
./manage.py add_rbac_static_forums
./manage.py add_rbac_static_payments
./manage.py add_rbac_static_orgs
./manage.py update_club_rbac_groups
./manage.py add_rbac_static_events
./manage.py add_rbac_static_notifications
./manage.py add_rbac_static_support
./manage.py add_rbac_static_club_sessions
./manage.py create_states
./manage.py add_notifications_templates

# If parameter core is passed then use the core files, not the user ones
if [ "$1" = "core" ]; then
  ./manage.py add_test_data --core_test_files
else
  ./manage.py add_test_data
fi

./manage.py add_additional_test_data_for_clubs

./manage.py add_test_data_forum_posts
