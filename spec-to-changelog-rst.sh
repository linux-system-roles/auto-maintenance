#!/bin/bash

# Usage: spec-to-changelog-rst.sh SPEC_FILE OUTPUT_RST_FILE [ MAJOR_VERSION_NUM ]
# Description: Generate the reStructuredText format changelog file from
#              the changelogs of the spec file.
# Details:
#   Read changelog section in SPEC_FILE.
#   Read the Bugzilla page specified with rhbz#.
#   In the RPM version section (e.g., [1.20.1-1] - 2022-09-27),
#   put the title with the bugzilla url depending in "New Features" or
#   "Bug Fix" depending upon the bugzilla type.
#   If there is a CHANGELOG.rst file in the current directory,
#   spec-to-changelog-rst.sh generates the changelogs newer than the
#   changelogs in the existing CHANGELOG.rst and merge the existing ones
#   into the newly generated changelog file.
#   The output reStructuredText file is OUTPUT_RST_FILE.
#   Note: By default, bug summaries belonging to RHEL 9 are put into the output.
#   E.g., bugs with (EL8) are skipped. The version could be altered if
#   MAJOR_VERSION_NUM is given.

set -euo pipefail

specfile="$1"
dest="$2"
# Major version to extract the info from bugzilla
target_version=${3:-"9"}

# If CHANGELOG.rst exists, add changelogs to the existing CHANGELOG.rst.
if [ -f CHANGELOG.rst ]; then
    grep -E "^\[[0-9]+\.[0-9]+\.[0-9]+-[0-9]+\] - " CHANGELOG.rst | head -n 1
    preversion=$( grep -E "^\[[0-9]+\.[0-9]+\.[0-9]+-[0-9]+\] - " CHANGELOG.rst | head -n 1 | sed -e "s/\[\(.*\)\] - .*/\1/" )
else
    # There's no rhbz set for this version and older ones.
    preversion="1.0.1-2"
fi

WORKDIR=$( mktemp -d /tmp/CHANGELOG.XXXX )
VFILE=$WORKDIR/Version
EFILE=$WORKDIR/Enhancement
BFILE=$WORKDIR/Bug
WORKFILE=$WORKDIR/CHANGELOG.rst
{ echo Changelog; echo =========; echo ""; } > "$WORKFILE"
print=false
while read -r line ; do
    if [ "$line" = %changelog ]; then
        print=true
        continue
    fi
    if [ "$print" = false ]; then
        continue
    fi
    if [[ "$line" =~ ^\*\ +[a-zA-Z]+\ +([a-zA-Z]+)\ +([0-9]+)\ +([0-9]+)\ .*-\ +([0-9.-]+)$ ]]; then
        if [ -f "$EFILE" ] || [ -f "$BFILE" ]; then
            cat "$VFILE"
            rm "$VFILE"
            if [ -f "$EFILE" ]; then
              cat "$EFILE"
              rm "$EFILE"
            fi
            if [ -f "$BFILE" ]; then
              cat "$BFILE"
              rm "$BFILE"
            fi
        fi
        mon="${BASH_REMATCH[1]}"
        day="${BASH_REMATCH[2]}"
        year="${BASH_REMATCH[3]}"
        version="${BASH_REMATCH[4]}"
        datestr=$(date --date="$mon $day $year" +%Y-%m-%d)
        if [[ $version == "$preversion" ]]; then
            break
        fi
        echo ["$version"] - "$datestr" > "$VFILE"
        echo ------------------------- >> "$VFILE"
        echo "" >> "$VFILE"
    elif [[ ( $line =~ .*rhbz#([0-9]+).* || $line =~ .*:\ rhbz#([0-9]+).* ) ]]; then
        # If (EL?), where ? is not $target_version (9), skip it.
        if [[ $line == *"(EL"* && $( expr "$line" : ".*EL$target_version" ) -eq 0 ]]; then
            continue
        fi
        # the extra spaces make markdown indent the following lines
        bz="${BASH_REMATCH[1]}"
        release=$( bugzilla query -b "$bz" --json | jq -r '.bugs[].cf_internal_target_release' )
        if [[ $release != $target_version\.* && $release != $target_version-* ]]; then
            continue
        fi
        role=$( bugzilla query -b "$bz" --json | jq -r '.bugs[].whiteboard' )
        if [ -n "$role" ]; then
            role=${role//role:/}
        fi
        bztype=$( bugzilla query -b "$bz" --json | jq -r '.bugs[].cf_type' )
        doctype=$( bugzilla query -b "$bz" --json | jq -r '.bugs[].cf_doc_type' )
        summary=$( bugzilla query -b "$bz" --json | jq -r '.bugs[].summary' )
        summary=$( echo "$summary" | sed -e "s/^RFE: //" -e "s/^\[RFE\] //" )
        if [[ $bztype == Enhancement || $doctype == Enhancement ]]; then
            currentfile="$EFILE"
            subtytle="New Features"
        else
            currentfile="$BFILE"
            subtytle="Bug Fix"
        fi

        if [ ! -f "$currentfile" ]; then
            echo "$subtytle" > "$currentfile"
            echo "~~~~~~~~~~~~" >> "$currentfile"
            echo "" >> "$currentfile"
        fi
        # If summary starts with the role name, header is not needed.
        if [[ -n "$role" && $( expr "$summary" : "$role" ) -ne ${#role} ]]; then
            header="$role - "
        else
            header=""
        fi
        echo "- \`$header$summary <https://bugzilla.redhat.com/show_bug.cgi?id=$bz>\`__" >> "$currentfile"
        echo "" >> "$currentfile"
    fi
done < "$specfile" >> "$WORKFILE"
if [ -f CHANGELOG.rst ]; then
    # Append existing CHANGELOG.rst to the generated one.
    lines=$( wc -l CHANGELOG.rst | awk '{print $1}' )
    lines=$(( lines - 3 ))
    tail -n "$lines" CHANGELOG.rst >> "$WORKFILE"
fi
cp "$WORKFILE" "$dest"
rm -rf "$WORKDIR"
