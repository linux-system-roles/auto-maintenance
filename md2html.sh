#!/bin/bash

set -euxo pipefail

convert_link=0
add_toc=0
toc_arg=""

while getopts "htl" opt; do
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
    t)
      add_toc=1
      toc_arg='--toc-levels 2..6'
      shift ;;
    *)
      ;;
  esac
done

for file in "$@"; do
  md2html_tool=""
  # RHEL 9 in brew cannot use pandoc, hence trying kramown first
  if type -p kramdown >/dev/null && kramdown -i GFM < /dev/null > /dev/null; then
    md2html_tool=kramdown
  elif type -p pandoc >/dev/null; then
    md2html_tool=pandoc
  fi
  # With kramdown, convert directly to HTML
  if [ "$md2html_tool" == kramdown ]; then
    if [ "$add_toc" -ne 0 ]; then
      sed -i '1s/^/* toc\n{:toc}\n/' "${file}"
    fi
    # Set locale to UTF-8 because by default it is set to US-ASCII
    LC_ALL=C.UTF-8 $md2html_tool --extension parser-gfm \
      --input GFM \
      "$toc_arg" \
      --output html "${file}" > "${file%.md}.html"
    if [ "$add_toc" -ne 0 ]; then
      sed -i '1,2d' "${file}"
    fi
  # With pandoc, convert to adoc, then to HTML
  elif [ "$md2html_tool" == pandoc ]; then
    $md2html_tool -f gfm "${file}" -t asciidoc -o "${file%.md}.tmp.adoc"
    touch -r "${file}" "${file%.md}.tmp.adoc"
    TZ=UTC asciidoc -o "${file%.md}.html" -a footer-style=none -a toc2 -a source-highlighter=highlight "${file%.md}.tmp.adoc"
    tr -d '\r' < "${file%.md}.html" > "${file%.md}.tmp.adoc"
    mv "${file%.md}.tmp.adoc" "${file%.md}.html"
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
