#!/bin/bash

# Get env variables.
EFS_MOUNT_DIR=`cat /opt/elasticbeanstalk/deployment/env | grep MOUNT_DIRECTORY | tr "=" " " | awk '{print $2}'`
EFS_FILE_SYSTEM_ID=`cat /opt/elasticbeanstalk/deployment/env | grep FILE_SYSTEM_ID | tr "=" " " | awk '{print $2}'`

echo "Mounting EFS filesystem ${EFS_FILE_SYSTEM_ID} to directory ${EFS_MOUNT_DIR} ..."

echo 'Stopping NFS ID Mapper...'
service rpcidmapd status &> /dev/null
if [ $? -ne 0 ] ; then
    echo 'rpc.idmapd is already stopped!'
else
    service rpcidmapd stop
    if [ $? -ne 0 ] ; then
        echo 'ERROR: Failed to stop NFS ID Mapper!'
        exit 0
    fi
fi

echo 'Checking if EFS mount directory exists...'
if [ ! -d ${EFS_MOUNT_DIR} ]; then
    echo "Creating directory ${EFS_MOUNT_DIR} ..."
    mkdir -p ${EFS_MOUNT_DIR}
    if [ $? -ne 0 ]; then
        echo 'ERROR: Directory creation failed!'
        exit 0
    fi
else
    echo "Directory ${EFS_MOUNT_DIR} already exists!"
fi

mountpoint -q ${EFS_MOUNT_DIR}
if [ $? -ne 0 ]; then
    echo "mount -t efs -o tls ${EFS_FILE_SYSTEM_ID}:/ ${EFS_MOUNT_DIR}"
    mount -t efs -o tls ${EFS_FILE_SYSTEM_ID}:/ ${EFS_MOUNT_DIR}
    if [ $? -ne 0 ] ; then
        echo 'ERROR: Mount command failed!'
        exit 0
    fi
    chmod 777 ${EFS_MOUNT_DIR}
    runuser -l  ec2-user -c "touch ${EFS_MOUNT_DIR}/it_works"
    if [[ $? -ne 0 ]]; then
        echo 'ERROR: Permission Error!'
        exit 0
    else
        runuser -l  ec2-user -c "rm -f ${EFS_MOUNT_DIR}/it_works"
    fi
else
    echo "Directory ${EFS_MOUNT_DIR} is already a valid mountpoint!"
fi

echo 'EFS mount complete.'

# The user and group should be wsgi but this doesn't transfer between
# instances. There is no access to the directories from elsewhere
# and the data is not critical so open to everyone.
echo 'Setting Permissions'
chmod 777 /cobalt-media/*

exit 0
