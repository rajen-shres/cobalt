#!/bin/bash

. ~/Development/c2/myenv/bin/activate
cd ~/Development/c2/cobalt
. ~/Dropbox/bin/cobalt_env.sh
export RDS_DB_NAME=test
./manage.py runserver 0.0.0.0:8088
exit
