#!/usr/bin/env python3
"""Inline a Sphinx HTML page's local assets into one self-contained file.

Turns the page plus its _static tree into a single HTML file, so one README.html
can be committed instead of the _static/ directory:

  - <link rel="stylesheet"> -> inlined <style> with @import and url() resolved to
    data: URIs. Fonts under a fonts/ dir are not inlined except KEEP_FONTS; they
    (and any missing url() target) are neutralized to url(data:,).
  - <img src="_static/..."> and favicon links -> data: URIs.
  - <script src="_static/..."> is inlined, or dropped with --drop-scripts.

External (http/https/data) references are left untouched.

Flags:
  --standalone    hide the docsite chrome (sidebar, breadcrumb, top bar, footer).
  --drop-scripts  drop <script> tags.
  --drop-fonts    inline no local font (smaller file; loses the icon-font glyphs).

Usage: html_to_singlefile.py [--drop-scripts] [--standalone] [--drop-fonts] INPUT.html OUTPUT.html
"""

import base64
import os
import re
import sys

# CSS injected by --standalone to hide the sphinx_rtd_theme chrome and the
# cross-page navigation, leaving only this role's content.
STANDALONE_CSS = """
.wy-nav-side, .wy-nav-top, .wy-breadcrumbs, .rst-footer-buttons { display: none !important; }
.wy-breadcrumbs + hr { display: none !important; }  /* rule left after hiding breadcrumbs */
.wy-nav-content-wrap { margin-left: 0 !important; background: #fff !important; }
.wy-nav-content { max-width: 900px; }
.DocSite-globalNav, .DocSite-nav { display: none !important; }
.rst-content .admonition-title:before { display: none !important; }
"""

MIME = {
    ".css": "text/css",
    ".js": "text/javascript",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
}

# Fonts to inline when found under a fonts/ dir; others are neutralized to keep
# the file small. The icon font has no system fallback, so keep it; text fonts
# fall back to the system sans-serif.
KEEP_FONTS = {"fontawesome-webfont.woff2"}


def is_external(url):
    return url.strip().startswith(("http://", "https://", "//", "data:", "about:", "#"))


def clean_relpath(url):
    """Strip ?query and #fragment from a relative asset reference."""
    return re.split(r"[?#]", url.strip(), maxsplit=1)[0]


def is_trimmed_font(url, keep_fonts):
    """True for a font under a fonts/ dir whose basename is not in keep_fonts.

    An empty keep_fonts drops every font (--drop-fonts).
    """
    rel = clean_relpath(url)
    parts = rel.replace("\\", "/").split("/")
    return "fonts" in parts[:-1] and os.path.basename(rel) not in keep_fonts


def read_bytes(base_dir, url):
    with open(os.path.join(base_dir, clean_relpath(url)), "rb") as fh:
        return fh.read()


def data_uri(base_dir, url):
    rel = clean_relpath(url)
    mime = MIME.get(os.path.splitext(rel)[1].lower(), "application/octet-stream")
    b64 = base64.b64encode(read_bytes(base_dir, url)).decode("ascii")
    return f"data:{mime};base64,{b64}"


def inline_css(css_text, css_dir, keep_fonts):
    """Return CSS with @import inlined and url(...) turned into data: URIs."""

    def repl_import(m):
        ref = m.group("u1") or m.group("u3")
        if not ref or is_external(ref):
            return m.group(0)
        try:
            imported = read_bytes(css_dir, ref).decode("utf-8")
        except OSError:
            return ""
        sub_dir = os.path.dirname(os.path.join(css_dir, clean_relpath(ref)))
        return inline_css(imported, sub_dir, keep_fonts)

    css_text = re.sub(
        r"""@import\s+(?:url\(\s*['"]?(?P<u3>[^'")]+)['"]?\s*\)"""
        r"""|['"](?P<u1>[^'"]+)['"])\s*;""",
        repl_import,
        css_text,
    )

    def repl_url(m):
        raw = m.group(1).strip().strip("'\"")
        if is_external(raw):
            return m.group(0)
        if is_trimmed_font(raw, keep_fonts):
            return "url(data:,)"  # trimmed font -> neutralized
        try:
            return f"url({data_uri(css_dir, raw)})"
        except OSError:
            return "url(data:,)"  # missing -> empty, self-contained

    return re.sub(r"url\(\s*([^)]+?)\s*\)", repl_url, css_text)


def main():
    args = sys.argv[1:]
    drop_scripts = "--drop-scripts" in args
    standalone = "--standalone" in args
    drop_fonts = "--drop-fonts" in args
    args = [
        a for a in args if a not in ("--drop-scripts", "--standalone", "--drop-fonts")
    ]
    if len(args) != 2:
        sys.exit(
            f"usage: {sys.argv[0]} [--drop-scripts] [--standalone] [--drop-fonts] "
            "INPUT.html OUTPUT.html"
        )
    in_path, out_path = args
    # --drop-fonts keeps no fonts; otherwise keep only KEEP_FONTS.
    keep_fonts = set() if drop_fonts else KEEP_FONTS
    base = os.path.dirname(os.path.abspath(in_path))
    with open(in_path, encoding="utf-8") as fh:
        html = fh.read()

    def repl_link(m):
        tag = m.group(0)
        href = re.search(r'href="([^"]+)"', tag)
        if not href or is_external(href.group(1)):
            return tag
        rel = clean_relpath(href.group(1))
        try:
            css = read_bytes(base, rel).decode("utf-8")
        except OSError:
            return tag
        css = inline_css(css, os.path.dirname(os.path.join(base, rel)), keep_fonts)
        return f"<style>\n{css}\n</style>"

    html = re.sub(r'<link\b[^>]*rel="stylesheet"[^>]*>', repl_link, html)

    def repl_script(m):
        tag = m.group(0)
        open_tag = re.match(r"<script\b[^>]*?>", tag).group(0)
        src = re.search(r'src="([^"]+)"', open_tag)
        if not src or is_external(src.group(1)):
            return tag
        if drop_scripts:
            return ""
        try:
            js = read_bytes(base, src.group(1)).decode("utf-8")
        except OSError:
            return tag
        js = js.replace("</script>", "<\\/script>")
        open_tag = re.sub(r'\s+src="[^"]+"', "", open_tag)
        return f"{open_tag}{js}</script>"

    html = re.sub(
        r"<script\b[^>]*\bsrc=\"[^\"]+\"[^>]*>\s*</script>", repl_script, html
    )

    def repl_img(m):
        tag = m.group(0)
        src = re.search(r'src="([^"]+)"', tag)
        if not src or is_external(src.group(1)):
            return tag
        try:
            return tag.replace(src.group(1), data_uri(base, src.group(1)))
        except OSError:
            return tag

    html = re.sub(r"<img\b[^>]*>", repl_img, html)

    def repl_icon(m):
        tag = m.group(0)
        href = re.search(r'href="([^"]+)"', tag)
        if not href or is_external(href.group(1)):
            return tag
        try:
            return tag.replace(href.group(1), data_uri(base, href.group(1)))
        except OSError:
            return tag

    html = re.sub(r'<link\b[^>]*rel="(?:shortcut )?icon"[^>]*>', repl_icon, html)

    if standalone:
        # Drop Sphinx's <head> navigation metadata links to other pages.
        html = re.sub(
            r'<link\b[^>]*rel="(?:index|search|next|prev)"[^>]*>\s*', "", html
        )
        # Drop the Ansible top bar: global nav + logo/title link (and its PNGs).
        html = re.sub(
            r'<div class="DocSite-globalNav[^"]*".*?</div>\s*', "", html, flags=re.S
        )
        html = re.sub(r'<a class="DocSite-nav[^"]*".*?</a>\s*', "", html, flags=re.S)

        # Neutralize links to other local pages; keep in-page anchors and external links.
        def repl_anchor(m):
            tag = m.group(0)
            href = re.search(r'href="([^"]*)"', tag)
            val = href.group(1).strip() if href else ""
            if not href or is_external(val) or val.startswith("#"):
                return tag
            target = clean_relpath(val)
            if target in ("", "/") or target.endswith(".html"):
                return re.sub(r'href="[^"]*"', 'href="#"', tag, count=1)
            return tag

        html = re.sub(r'<a\b[^>]*href="[^"]*"[^>]*>', repl_anchor, html)
        # Neutralize any form posting to a local page (e.g. the search box).
        html = re.sub(
            r'(<form\b[^>]*\baction=")[^"]*\.html[^"]*(")',
            r"\1#\2",
            html,
        )
        html = html.replace("</head>", f"<style>{STANDALONE_CSS}</style>\n</head>", 1)

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)


if __name__ == "__main__":
    main()
