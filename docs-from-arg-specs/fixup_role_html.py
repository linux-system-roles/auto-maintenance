#!/usr/bin/env python3
"""Clean up antsibull's rendered role HTML page in place.

Run before README.html and README.md are generated from the page, so both
inherit the changes. Two fixups:

  1. Remove the "This role is part of the <collection>" note antsibull prepends.
  2. Optionally rewrite the title's role name. antsibull titles the page
     "<namespace>.<collection>.<role> role -- ...". When ROLE_NAME is given, the
     leading FQCN token is replaced in both the <h1> heading and the <title>
     element, e.g. "bootloader role -- ...".

Targeted regex substitutions are used (not an HTML parser) so the rest of the
document is left byte-for-byte unchanged -- matching html_to_singlefile.py, which
also edits this HTML in place. Parsing and reserializing with an HTML library
would reorder attributes, decode entities (&#64;, &mdash;), and change void-tag
spacing, bloating README.html's diff and undoing antsibull's deliberate escaping.

Usage: fixup_role_html.py HTML_FILE [ROLE_NAME]
  HTML_FILE   the Sphinx-rendered role page, edited in place
  ROLE_NAME   if given, the name to put in the title in place of the FQCN
"""

import re
import sys

# --- Collection note removal ------------------------------------------------
# An "admonition note" div. The note has no nested <div>, so a non-greedy match
# to the first </div> is safe. Any note that is not the collection boilerplate is
# left untouched (see COLLECTION_NOTE_MARKERS).
NOTE_RE = re.compile(r'\s*<div class="admonition note">.*?</div>', re.S)

# The collection boilerplate is identified by a distinctive sentence from its
# body: "It is not included in ansible-core. To check whether it is installed,
# run ansible-galaxy collection list." antsibull wraps "ansible-core" and the
# command in inline <code> tags, so match the plain-text fragments around them
# rather than the whole sentence -- this does not depend on the exact markup.
COLLECTION_NOTE_MARKERS = (
    "It is not included in",
    "To check whether it is installed, run",
)


def strip_collection_note(html):
    """Drop the antsibull collection note; leave every other note in place."""

    def replace(match):
        block = match.group(0)
        if all(marker in block for marker in COLLECTION_NOTE_MARKERS):
            return ""
        return block

    return NOTE_RE.sub(replace, html)


# --- Title role-name rewrite ------------------------------------------------
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


def fixup(html, role_name=None):
    """Strip the collection note and, if role_name is given, rewrite the title."""
    html = strip_collection_note(html)
    if role_name is not None:
        html = rewrite_role_name(html, "title", role_name)
        html = rewrite_role_name(html, "h1", role_name)
    return html


def main(argv):
    """Clean up HTML_FILE in place; rewrite the title to ROLE_NAME if given."""
    if len(argv) not in (2, 3):
        sys.exit(f"usage: {argv[0]} HTML_FILE [ROLE_NAME]")
    html_file = argv[1]
    role_name = argv[2] if len(argv) == 3 else None

    with open(html_file, encoding="utf-8") as handle:
        html = handle.read()

    html = fixup(html, role_name)

    with open(html_file, "w", encoding="utf-8") as handle:
        handle.write(html)


if __name__ == "__main__":
    main(sys.argv)
