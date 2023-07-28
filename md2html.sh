#!/bin/bash

set -euxo pipefail

convert_link=0

while getopts "hl" opt; do
  case "$opt" in
    h)
      echo "Usage: $0 [-h] [[-l] md_file0 md_file1 ...]"
      echo "options:"
      echo "-l  convert links to other md files to html"
      echo "-t  add TOC to the converted HTML doc. Available for kramdown only."
      exit ;;
    l)
      convert_link=1
      shift ;;
    *)
      ;;
  esac
done

for file in "$@"; do
  # RHEL 9 in brew cannot use pandoc, hence trying kramown first
  if [ -z "${md2html_tool:-}" ]; then
    if type -p kramdown >/dev/null && kramdown -i GFM < /dev/null > /dev/null; then
      md2html_tool=kramdown
    elif type -p pandoc >/dev/null; then
      md2html_tool=pandoc
    fi
  fi
  if [ "$md2html_tool" == kramdown ]; then
    sed -i '1s/^/* toc\n{:toc}\n/' "${file}"
    # Set locale to UTF-8 because by default it is set to US-ASCII
    # shellcheck disable=SC2086
    LC_ALL=C.UTF-8 $md2html_tool --extension parser-gfm \
      --input GFM \
      --toc-levels "2..6" \
      --output html "${file}" > "${file%.md}.html"
    sed -i '1,2d' "${file}"
  elif [ "$md2html_tool" == pandoc ]; then
    $md2html_tool -f gfm "${file}" -t asciidoc -o "${file%.md}.tmp.adoc"
    touch -r "${file}" "${file%.md}.tmp.adoc"
    TZ=UTC asciidoc -o "${file%.md}.html" -a footer-style=none -a toc2 -a source-highlighter=highlight "${file%.md}.tmp.adoc"
    tr -d '\r' < "${file%.md}.html" > "${file%.md}.tmp.adoc"
    mv "${file%.md}.tmp.adoc" "${file%.md}.html"
  elif [ "$md2html_tool" == pandoc-new ]; then
    pandoc --from gfm "${file}" --to html5 --output "${file%.md}.html" \
      --toc --shift-heading-level-by=-1 \
      --template .GitHub.html5
  else
    echo "Cannot find a tool to convert md to adoc"
    echo "You must install rubygem-kramdown-parser-gfm or pandoc"
    exit 1
  fi

  # Convert links
  if [ "$convert_link" -ne 0 ]; then
    sed -i -e "s/\.md\>/\.html/g" "${file%.md}.html"
  fi
done
