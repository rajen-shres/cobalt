#!/bin/bash

. ~/Development/c2/myenv/bin/activate
cd ~/Development/c2/cobalt
. ~/Dropbox/bin/cobalt_env.sh
export RDS_DB_NAME=test
# Run with coverage -p stores the data in a different file
coverage run -p manage.py runserver 0.0.0.0:8088 --noreload
exit
