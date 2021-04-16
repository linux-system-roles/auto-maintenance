#!/bin/bash

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    echo "Description - Verify rpm package count with various combination of ansible and collection_artifact options."
    echo "            - Check there is no README.html files in /usr/share/andible/collections."
    echo "Usage: $0 [ -h | --help ] | [ fedpkg | rhpkg [ branch_name ] ]"
    exit 0
fi

if [ "$( find . -maxdepth 1 -name '*.spec' | wc -l )" -ne 1 ]; then
    echo There must exactly 1 spec file in "$( pwd )".
    exit 1
fi

set -euo pipefail

pkgcmd=${1:-"fedpkg"}
branch=${2:-"rawhide"}
run() {
    local option=$1
    local ext=$2
    local expect=$3
    rm -rf noarch
    output=/tmp/$pkgcmd.$ext
    cmdline="$pkgcmd --release $branch local $option"
    echo "$cmdline"
    $cmdline > "$output" 2>&1
    count=$( find noarch -name "*.rpm" | wc -l )
    if [ "$count" -eq "$expect" ]; then
      echo OK - result "$count" is "$expect"
    else
      echo FAILED - result "$count" is not "$expect"
    fi

    filename=$( "$pkgcmd" --release "$branch" verrel )
    if rpm -qlp noarch/"${filename}"*.rpm | grep -F '.html' | grep collection | grep -v '/usr/share/doc/'; then
      echo FAILED - '.html' files are in noarch/"${filename}"*.rpm other than doc
    else
      echo OK - '.html' files are only in doc in noarch/"${filename}"*.rpm
    fi
}

run "--without ansible" "without_ansible" 1
run "--without ansible --with collection_artifact" "without_ansible-with_collection_artifact" 1
run "--without ansible --without collection_artifact" "without_ansible-without_collection_artifact" 1
run "--without collection_artifact" "without_collection_artifact" 1
run "--with ansbile --without collection_artifact" "with_ansible-without_collection_artifact" 1
run "" "no_opt" 1
run "--with ansbile" "with_ansible" 1
run "--with collection_artifact" "with_collection_artifact" 2
run "--with ansible --with collection_artifact" "with_ansible-with_collection_artifact" 2
