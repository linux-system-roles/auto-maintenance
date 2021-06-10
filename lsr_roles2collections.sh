#!/bin/bash

COLLECTION_SRC_PATH=${COLLECTION_SRC_PATH:-"${HOME}/linux-system-roles"}
COLLECTION_DEST_PATH=${COLLECTION_DEST_PATH:-"${HOME}/.ansible/collections"}
COLLECTION_SRC_OWNER=${COLLECTION_SRC_OWNER:-"linux-system-roles"}
COLLECTION_NAMESPACE=${COLLECTION_NAMESPACE:-"fedora"}
COLLECTION_NAME=${COLLECTION_NAME:-"linux_system_roles"}

ROLES=${ROLES:-"certificate cockpit crypto_policies firewall ha_cluster kdump kernel_settings logging metrics nbde_client nbde_server network postfix selinux sshd storage timesync tlog vpn"}
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
    fi
    cd "$CWD" || exit
    python lsr_role2collection.py --readme lsr_role2collection/collection_readme.md --role "$role" --src-owner "$COLLECTION_SRC_OWNER" --namespace "$COLLECTION_NAMESPACE" --collection "$COLLECTION_NAME"
done
