#!/bin/bash

set -euxo pipefail
convert_link=0
while getopts "hl" opt; do
	case "$opt" in
		h)
			echo "Usage: $0 [-h] [[-l] md_file0 md_file1 ...]"
			exit ;;
		l)
			convert_link=1
			shift ;;
		*)
			;;
	esac
done

for file in "$@"; do
	pandoc -f markdown_github "${file}" -t asciidoc -o "${file%.md}.tmp.adoc"
	if [ "$convert_link" -ne 0 ]; then
		sed -i -e "s/\.md\>/\.html/g" "${file%.md}.tmp.adoc"
	fi
	touch -r "${file}" "${file%.md}.tmp.adoc"
	TZ=UTC asciidoc -o "${file%.md}.html" -a footer-style=none -a toc2 -a source-highlighter=highlight "${file%.md}.tmp.adoc"
	tr -d '\r' < "${file%.md}.html" > "${file%.md}.tmp.adoc"
	mv "${file%.md}.tmp.adoc" "${file%.md}.html"
done
