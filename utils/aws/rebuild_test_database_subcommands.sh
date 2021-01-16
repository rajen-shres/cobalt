#!/bin/sh

./manage.py migrate
./manage.py createsu
./manage.py create_abf
./manage.py add_rbac_static_forums
./manage.py add_rbac_static_payments
./manage.py add_rbac_static_orgs
./manage.py add_rbac_static_events
./manage.py add_rbac_static_notifications
./manage.py create_states
./manage.py add_test_data
#./manage.py createdummyusers
#./manage.py importclubs
