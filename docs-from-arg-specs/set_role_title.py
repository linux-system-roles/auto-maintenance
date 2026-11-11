#!/usr/bin/env python3
"""Rewrite the role title in the Sphinx-rendered role HTML page, in place.

antsibull titles the page '<namespace>.<collection>.<role> role -- ...'. This
replaces the leading collection FQCN with the short (legacy) role name, e.g.
'bootloader role -- ...', in both the <h1> heading and the <title> element.
README.html and README.md are both generated from this page afterwards, so both
inherit the change and no further rewriting is needed downstream.

Usage: set_role_title.py HTML_FILE ROLE_NAME
"""

import re
import sys

from bs4 import BeautifulSoup

# The title text is "<fqcn> role -- ..."; replace the <fqcn> token (no spaces)
# with the short role name, preserving leading space and the " role" that
# follows (and whatever comes after it, e.g. " -- <short_description>", or the
# " -- Ansible collections documentation" chrome in the <title>).
FQCN_RE = re.compile(r"^(\s*)\S+(\s+role\b)")


def rewrite_first_role_text(tag, role_name):
    """Rewrite the first text child of tag that holds the "<fqcn> role" title."""
    if tag is None:
        return
    for child in tag.children:
        if isinstance(child, str) and " role" in child:
            rewritten = FQCN_RE.sub(
                lambda match: f"{match.group(1)}{role_name}{match.group(2)}",
                child,
                count=1,
            )
            if rewritten != child:
                child.replace_with(rewritten)
            break


def main(argv):
    """Rewrite the role title in HTML_FILE in place to use ROLE_NAME."""
    if len(argv) != 3:
        sys.exit(f"usage: {argv[0]} HTML_FILE ROLE_NAME")
    html_file, role_name = argv[1], argv[2]

    with open(html_file, encoding="utf-8") as handle:
        soup = BeautifulSoup(handle.read(), "html.parser")

    # <h1>: a trailing headerlink anchor is a separate child, left untouched.
    rewrite_first_role_text(soup.find("h1"), role_name)
    # <title>: the browser/tab title (keeps its " -- ... documentation" suffix).
    rewrite_first_role_text(soup.find("title"), role_name)

    with open(html_file, "w", encoding="utf-8") as handle:
        handle.write(str(soup))


if __name__ == "__main__":
    main(sys.argv)
