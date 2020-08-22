#!/bin/bash

COLLECTION_SRC_PATH=${COLLECTION_SRC_PATH:-"${HOME}/linux-system-roles"}
COLLECTION_DEST_PATH=${COLLECTION_DEST_PATH:-"${HOME}/collections"}
ROLES=${ROLES:-"certificate kdump kernel_settings logging metrics nbde_client nbde_server network selinux storage timesync tlog tuned"}
CWD=$(pwd)

export COLLECTION_SRC_PATH COLLECTION_DEST_PATH

if [ ! -d "$COLLECTION_SRC_PATH" ]; then
    mkdir -p "$COLLECTION_SRC_PATH"
fi
if [ ! -d "$COLLECTION_DEST_PATH" ]; then
    mkdir -p "$COLLECTION_DEST_PATH"
fi
for role in $ROLES
do
    if [ ! -d "$COLLECTION_SRC_PATH/$role" ]; then
        cd "$COLLECTION_SRC_PATH" || exit
        git clone https://github.com/linux-system-roles/"$role"
    else
        cd "$COLLECTION_SRC_PATH/$role" || exit
        git branch
        git stash
        git checkout master
        git pull
    fi
    cd "$CWD" || exit
    python lsr-role2collection.py --role "$role"
done
role="template"
if [ ! -d "$COLLECTION_SRC_PATH/$role" ]; then
    cd "$COLLECTION_SRC_PATH" || exit
    git clone https://github.com/linux-system-roles/"$role"
else
    cd "$COLLECTION_SRC_PATH/$role" || exit
    git branch
    git stash
    git checkout master
    git pull
fi
cd "$CWD" || exit
python lsr-role2collection.py --molecule
