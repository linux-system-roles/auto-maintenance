#!/usr/bin/env python3
"""Rewrite the role name in the Sphinx-rendered role HTML page, in place.

antsibull titles the page '<namespace>.<collection>.<role> role -- ...'. This
replaces the leading collection FQCN with the given (e.g. short) role name in
both the <h1> heading and the <title> element, e.g. 'bootloader role -- ...'.
README.html and README.md are both generated from this page afterwards, so both
inherit the change.

A targeted regex substitution is used (not an HTML parser) so the rest of the
document is left byte-for-byte unchanged -- matching html_to_singlefile.py,
which also edits this HTML in place. Parsing the page with an HTML library and
writing it back would reserialize the whole document (reordering attributes,
decoding entities such as &#64; and &mdash;, changing void-tag spacing), which
would bloat README.html's diff and undo antsibull's deliberate escaping.

Usage: set_role_title.py HTML_FILE ROLE_NAME
"""

import re
import sys


def rewrite_role_name(html, tag, role_name):
    """Replace the "<fqcn> role" token in the first <tag> element with role_name.

    Anchors on the opening <tag ...> (so the match starts at the title text),
    captures the leading non-space token -- the FQCN, which contains no spaces or
    "<" -- immediately followed by " role", and swaps just that token for
    role_name. Only the first match is changed; the " role", the "-- ..." suffix
    and everything else are preserved. If the expected shape is not found, the
    HTML is returned unchanged.
    """
    pattern = re.compile(r"(<" + re.escape(tag) + r"\b[^>]*>\s*)([^<\s]+)(\s+role\b)")
    return pattern.sub(
        lambda match: f"{match.group(1)}{role_name}{match.group(3)}",
        html,
        count=1,
    )


def main(argv):
    """Rewrite the role title in HTML_FILE in place to use ROLE_NAME."""
    if len(argv) != 3:
        sys.exit(f"usage: {argv[0]} HTML_FILE ROLE_NAME")
    html_file, role_name = argv[1], argv[2]

    with open(html_file, encoding="utf-8") as handle:
        html = handle.read()

    html = rewrite_role_name(html, "title", role_name)
    html = rewrite_role_name(html, "h1", role_name)

    with open(html_file, "w", encoding="utf-8") as handle:
        handle.write(html)


if __name__ == "__main__":
    main(sys.argv)
