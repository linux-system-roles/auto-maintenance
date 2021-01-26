#!/bin/bash

set -euxo pipefail

for file in "$@"; do
	pandoc -f markdown_github "${file}" -t asciidoc -o "${file%.md}.tmp.adoc"
	touch -r "${file}" "${file%.md}.tmp.adoc"
	TZ=UTC asciidoc -o "${file%.md}.html" -a footer-style=none -a toc2 -a source-highlighter=highlight "${file%.md}.tmp.adoc"
	rm "${file%.md}.tmp.adoc"
done
