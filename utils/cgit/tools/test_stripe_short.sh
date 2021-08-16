#!/bin/bash

. ~/Development/c2/myenv/bin/activate
cd ~/Development/c2/cobalt
. ~/Dropbox/bin/cobalt_env.sh
export RDS_DB_NAME=test
stripe listen --forward-to 127.0.0.1:8088/payments/stripe-webhook
exit