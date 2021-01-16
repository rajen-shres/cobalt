#!/bin/bash

###########################
# Install utility scripts #
###########################


cp /root/.bashrc /root/.bashrc.old

# ec2-user bash login script
cat << EOF > /home/ec2-user/.bashrc
#!/bin/bash
# Source global definitions
if [ -f /etc/bashrc ]; then
	. /etc/bashrc
fi
# Pretty much everything requires root so su immediately
alias x='exit'
# check if interactive shell or not
if [ -t 0 ]
then
   sudo -s
fi

EOF

# root bash login script
cat << EOF > /root/.bashrc
# Source global definitions
if [ -f /etc/bashrc ]; then
	. /etc/bashrc
fi

#!/bin/bash
# root now so do stuff
alias x='exit'

# activate virtualenv
. /var/app/venv/staging-LQM1lest/bin/activate

# set environment variables
\`cat /opt/elasticbeanstalk/deployment/env | awk '{print "export",\$1}'\`

# change to app directory
cd /var/app/current

clear
echo \$COBALT_HOSTNAME
cat /cobalt-media/admin/env.txt
EOF

# tlog command
cat << EOF > /usr/local/bin/tlog
#!/bin/bash

clear
echo
echo Logs live in /var/log
echo
PS3='Select a log file: '
options=("eb-engine.log (install file)" "eb-hooks.log (install file details)" "web.stdout.log (stdout/stderr)" "nginx/access.log (web access log)" "nginx/access.log (web access log filtered)" "nginx/error.log (web error log)" "Quit")
select opt in "\${options[@]}"
do
    case \$opt in
        "eb-engine.log (install file)")
            tail -100f /var/log/eb-engine.log
            break
            ;;
        "eb-hooks.log (install file details)")
            tail -100f /var/log/eb-hooks.log
            break
          ;;
        "web.stdout.log (stdout/stderr)")
            tail -1000f /var/log/web.stdout.log | grep -v "Invalid HTTP_HOST"
            break
            ;;
        "nginx/access.log (web access log)")
            tail -1000f /var/log/nginx/access.log
            break
            ;;
        "nginx/access.log (web access log filtered)")
            tail -1000f /var/log/nginx/access.log | grep -v HealthChecker
            break
            ;;
        "nginx/error.log (web error log)")
            tail -1000f /var/log/nginx/error.log
            break
            ;;
        "Quit")
            break
            ;;
        *) echo "invalid option ";;
    esac
done
EOF
chmod 755 /usr/local/bin/tlog

# help file
cat << EOF > /usr/local/bin/h
echo
echo files
echo /opt/elasticbeanstalk/deploy/env - environment vars
echo /etc/nginx     \t\t\t                  - nginx config
echo
echo Commands
echo nginx -t                         - test config

EOF
chmod 755 /usr/local/bin/h
