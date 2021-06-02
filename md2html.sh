#!/bin/bash

set -euxo pipefail

convert_link=0

while getopts "hl" opt; do
  case "$opt" in
    h)
      echo "Usage: $0 [-h] [[-l] md_file0 md_file1 ...]"
      echo "options:"
      echo "-l  convert links to other md files to html"
      exit ;;
    l)
      convert_link=1
      shift ;;
    *)
      ;;
  esac
done

md2html_tool=""
# RHEL 9 in brew cannot use pandoc, hence trying kramdown first
if type -p kramdown >/dev/null && kramdown < /dev/null > /dev/null; then
  md2html_tool=kramdown
elif type -p pandoc >/dev/null; then
  md2html_tool=pandoc
else
  echo "Cannot find a tool to convert md to adoc"
  echo "You must install rubygem-kramdown-parser-gfm or pandoc"
  exit 1
fi

# Convert codeblock to depth 4 indent
function conv_codeblock_to_indent() {
  file="${1}"
  IFS=''
  IN=0
  while read -r line ; do
    if [[ $line == \`\`\`* ]] ; then
      if [[ $IN -eq 0 ]]; then
        IN=1
      else
        IN=0
      fi
    elif [[ $IN -eq 0 ]]; then
      echo "$line" >> "${2}"
    else
      echo "  $line" >> "${2}"
    fi
  done < "${1}"
}

tmpfile=$( mktemp md2html.XXXXXX )
trap 'rm -f ${tmpfile}' ABRT EXIT HUP INT QUIT
for file in "$@"; do
  if [ ! -f "${file}" ]; then
    continue
  fi
  echo "" > "${tmpfile}"
  conv_codeblock_to_indent "${file}" "${tmpfile}"
  # With kramdown, convert directly to HTML
  if [ "$md2html_tool" == kramdown ]; then
    # Set locale to UTF-8 because by default it is set to US-ASCII
    LC_ALL=C.UTF-8 $md2html_tool --input kramdown --output html "${tmpfile}" > "${file%.md}.html"
  # With pandoc, convert to adoc, then to HTML
  elif [ "$md2html_tool" == pandoc ]; then
    $md2html_tool -f markdown_github "${tmpfile}" -t asciidoc -o "${file%.md}.tmp.adoc"
    touch -r "${tmpfile}" "${file%.md}.tmp.adoc"
    TZ=UTC asciidoc -o "${file%.md}.html" -a footer-style=none -a toc2 -a source-highlighter=highlight "${file%.md}.tmp.adoc"
    tr -d '\r' < "${file%.md}.html" > "${file%.md}.tmp.adoc"
    mv "${file%.md}.tmp.adoc" "${file%.md}.html"
  fi

  # Convert links
  if [ "$convert_link" -ne 0 ]; then
    sed -i -e "s/\.md\>/\.html/g" "${file%.md}.html"
  fi
done
