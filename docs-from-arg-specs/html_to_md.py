#!/usr/bin/env python3
"""Convert the Sphinx-rendered role HTML page into README.md.

Prose is converted with pandoc (HTML -> GFM); the Parameters/Attributes/
Return-Variables tables are rebuilt as Markdown pipe tables by walking antsibull's
option-table markup with BeautifulSoup. The parser relies on antsibull's classes
and anchor ids (ansible-option-table; parameter-main--/return-/attribute- ids;
ansible-option-type-line; ul.simple choices; the Default:/Returned: lines), so it
may need updating if that markup changes.

Usage: html_to_md.py SPHINX_HTML_PAGE OUTPUT_README_MD
"""

import re
import subprocess
import sys

from bs4 import BeautifulSoup

NEST_MARKER = "\N{BULLET} "  # one per nesting level in the Parameter/Key column


# --- pandoc + text helpers -------------------------------------------------


def run_pandoc(fragment):
    """Convert an HTML fragment to GitHub-Flavored Markdown (raw, multi-line)."""
    return subprocess.run(
        ["pandoc", "-f", "html", "-t", "gfm", "--wrap=none"],
        input=fragment,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def collapse(text):
    """Squeeze all runs of whitespace (incl. newlines) into single spaces."""
    return " ".join(text.split())


def pandoc_inline_many(fragments):
    """Convert many HTML fragments in one pandoc call, one output line each.

    Pipe-table cells must be a single source line, so each result is collapsed
    onto one line. The fragments are joined with a unique marker paragraph and
    converted together (one subprocess instead of one per cell), then the output
    is split back apart on that marker.

    Returns a list of Markdown strings, one per input fragment (same order).
    """
    if not fragments:
        return []
    marker = "@@CELLBREAK@@"
    joined = f"\n\n<p>{marker}</p>\n\n".join(frag or "<p></p>" for frag in fragments)
    pieces = run_pandoc(joined).split(marker)
    return [collapse(piece) for piece in pieces]


def esc_cell(text):
    """Escape the pipe character so cell content cannot break the table."""
    return text.replace("|", "\\|")


def gh_slug(text):
    """Return the heading anchor GitHub derives from a heading's text."""
    slug = text.strip().lower()
    slug = re.sub(r"[^\w\- ]", "", slug)  # drop the punctuation GitHub removes
    return slug.replace(" ", "-")


def format_pipe_table(headers, rows):
    """Render a Markdown pipe table with space-aligned columns.

    Cells are padded so the column borders line up in the raw Markdown; the extra
    spaces are valid GFM and are stripped when rendered. The final column is left
    ragged (its cells are long single lines).

    headers is the list of column names; rows is a list of already-escaped cell
    lists, one per column.
    """
    last = len(headers) - 1
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def line(cells):
        padded = [
            cell if index == last else cell.ljust(widths[index])
            for index, cell in enumerate(cells)
        ]
        return "| " + " | ".join(padded) + " |"

    separator = [
        "---" if index == last else "-" * widths[index] for index in range(len(headers))
    ]
    return "\n".join([line(headers), line(separator), *(line(row) for row in rows)])


# --- option-table parsing (BeautifulSoup) ----------------------------------


def data_rows(table):
    """Yield the list of data <td> tags for each non-header row of a table."""
    for tr in table.find_all("tr"):
        if tr.find("th"):
            continue
        tds = tr.find_all("td")
        if tds:
            yield tds


def option_cell(td):
    """Return the inner <div class="ansible-option-cell">, or the <td> itself."""
    return td.find("div", class_="ansible-option-cell") or td


def anchor_path(td, prefix):
    """Return the slash-separated path from a '<prefix>PATH' anchor id in a cell.

    The number of slashes gives the option/return nesting depth. Exits if the
    expected anchor is missing (antsibull's markup likely changed).
    """
    anchor = td.find(id=re.compile("^" + re.escape(prefix)))
    if anchor is None:
        sys.exit(
            f"error: no '{prefix}...' anchor id in the role HTML; antsibull's "
            "markup likely changed (see this script's module docstring)"
        )
    start = len(prefix)
    return anchor["id"][start:]


def type_text(td):
    """Return the option's type line ('boolean', 'list / elements=dictionary')."""
    line = td.find("p", class_="ansible-option-type-line")
    return collapse(line.get_text()) if line else ""


def nested_label(td, prefix):
    """Build a name-column label: bullet-nesting + **name** *type*.

    Shared by Parameters ("parameter-main--...") and Return Values ("return-...").
    """
    path = anchor_path(td, prefix)
    label = f"**{path.split('/')[-1]}**"
    the_type = type_text(td)
    if the_type:
        label += f" *{the_type}*"  # type inline after the name, italic
    return NEST_MARKER * path.count("/") + label  # one marker per nesting level


def split_description(cell):
    """Return (description_html, suffix_md) for an option comment cell.

    The description is everything before the first Choices list (ul.simple) or
    option line (p.ansible-option-line); the suffix is the inline "Choices:" or
    "Default:" text rendered directly (without pandoc).
    """
    desc_nodes = []
    for child in cell.children:
        classes = getattr(child, "get", lambda _: None)("class") or []
        if getattr(child, "name", None) == "ul" and "simple" in classes:
            break
        if getattr(child, "name", None) == "p" and "ansible-option-line" in classes:
            break
        desc_nodes.append(child)
    desc_html = "".join(str(node) for node in desc_nodes).strip()

    choices = cell.find("ul", class_="simple")
    if choices:
        values = []
        for item in choices.find_all("li"):
            code = item.find("code")
            value = code.get_text().strip() if code else ""
            classes = code.get("class") or [] if code else []
            default = " (default)" if "ansible-option-default-bold" in classes else ""
            values.append(f"`{value}`{default}")
        return desc_html, "**Choices:** " + ", ".join(values)

    # Options without choices may carry a standalone Default: line.
    strong = cell.find("strong", class_="ansible-option-default-bold")
    if strong:
        code = strong.parent.find("code")
        value = code.get_text().strip() if code else ""
        if value:
            return desc_html, f"**Default:** `{value}`"
    return desc_html, ""


def build_parameters(table):
    """Rebuild the Parameters table as a space-aligned pipe table with nesting."""
    labels, cells = [], []
    for tds in data_rows(table):
        labels.append(nested_label(tds[0], "parameter-main--"))
        cells.append(option_cell(tds[1]))
    parsed = [split_description(cell) for cell in cells]
    descriptions = pandoc_inline_many([desc for desc, _ in parsed])
    rows = []
    for label, (_, suffix), description in zip(labels, parsed, descriptions):
        comment = " ".join(part for part in (description, suffix) if part)
        rows.append([esc_cell(label), esc_cell(comment)])
    return format_pipe_table(["Parameter", "Comments"], rows)


def build_attributes(table):
    """Rebuild the Attributes table (Attribute / Support / Description)."""
    names, supports_html, descriptions_html = [], [], []
    for tds in data_rows(table):
        names.append(anchor_path(tds[0], "attribute-"))
        support = option_cell(tds[1])
        # Drop the redundant "Support:" label (the column header already says it).
        label = support.find("strong", class_="ansible-attribute-support-label")
        if label:
            label.decompose()
        supports_html.append(support.decode_contents())
        descriptions_html.append(option_cell(tds[2]).decode_contents())
    supports = pandoc_inline_many(supports_html)
    descriptions = pandoc_inline_many(descriptions_html)
    rows = [
        [esc_cell(f"**{name}**"), esc_cell(support), esc_cell(description)]
        for name, support, description in zip(names, supports, descriptions)
    ]
    return format_pipe_table(["Attribute", "Support", "Description"], rows)


def build_returns(table):
    """Rebuild the Return Values table (Key / Description) with nesting.

    The description cell carries the "Returned:" (and any "Sample:") lines as
    extra paragraphs, which pandoc_inline_many folds onto the single line a
    pipe-table cell requires.
    """
    labels, descriptions_html = [], []
    for tds in data_rows(table):
        labels.append(nested_label(tds[0], "return-"))
        descriptions_html.append(option_cell(tds[1]).decode_contents())
    descriptions = pandoc_inline_many(descriptions_html)
    rows = [
        [esc_cell(label), esc_cell(description)]
        for label, description in zip(labels, descriptions)
    ]
    return format_pipe_table(["Key", "Description"], rows)


# --- page cleanup ----------------------------------------------------------


def strip_chrome(body):
    """Remove Sphinx/antsibull scaffolding that does not belong in Markdown."""
    for span in body.find_all("span"):
        span.unwrap()  # flatten per-word <span> wrappers into clean text
    # Point the local contents TOC at GitHub-style in-file anchors, keeping only
    # href (no id/class) so pandoc renders clean Markdown links, not raw HTML.
    nav = body.find("nav", class_="contents")
    if nav:
        for link in nav.find_all("a", class_="internal"):
            link.attrs = {"href": "#" + gh_slug(link.get_text())}
    # Flatten the remaining in-page cross-references (no anchors in a flat README);
    # external links ("reference external") are left to become Markdown links.
    for link in body.find_all("a", class_="internal"):
        link.unwrap()
    # The admonition box is gone in Markdown, so its bare "Note" title is noise.
    for title in body.find_all("p", class_="admonition-title"):
        title.decompose()
    for link in body.find_all("a", class_="headerlink"):
        link.decompose()
    for link in body.find_all("a", class_="toc-backref"):
        link.unwrap()
    # Drop classes from the remaining (external) links so pandoc emits clean
    # Markdown links instead of keeping the whole anchor as raw HTML.
    for link in body.find_all("a", class_=True):
        del link["class"]


def replace_code_blocks(body):
    """Swap Sphinx highlight blocks for placeholders; return {placeholder: md}.

    pandoc would render them as indented code blocks, so instead emit fenced
    ```yaml blocks (the Examples use YAML) and splice them back after pandoc.
    """
    blocks = {}

    def is_highlight(tag):
        classes = tag.get("class") or []
        return tag.name == "div" and any(c.startswith("highlight-") for c in classes)

    for div in body.find_all(is_highlight):
        pre = div.find("pre")
        if pre is None:
            continue
        key = f"@@CODE{len(blocks)}@@"
        blocks[key] = "```yaml\n" + pre.get_text().strip("\n") + "\n```"
        div.replace_with(placeholder(body, key))
    return blocks


def replace_tables(body):
    """Swap each antsibull option table for a placeholder; return {placeholder: md}.

    pandoc never sees the HTML tables (it would mangle them). Parameters,
    Attributes and Return Values tables are told apart by their anchor ids.
    """
    built = {}
    tables = body.find_all("table", class_=re.compile("ansible-option-table"))
    for index, table in enumerate(tables):
        key = f"@@TABLE{index}@@"
        if table.find(id=re.compile("^parameter-main--")):
            built[key] = build_parameters(table)
        elif table.find(id=re.compile("^return-")):
            built[key] = build_returns(table)
        else:
            built[key] = build_attributes(table)
        table.replace_with(placeholder(body, key))
    return built


def placeholder(body, key):
    """Return a <p>KEY</p> tag pandoc will pass through verbatim."""
    tag = BeautifulSoup("", "html.parser").new_tag("p")
    tag.string = key
    return tag


def main():
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} SPHINX_HTML_PAGE OUTPUT_README_MD")
    html_path, md_path = sys.argv[1], sys.argv[2]

    with open(html_path, encoding="utf-8") as handle:
        soup = BeautifulSoup(handle.read(), "html.parser")
    body = soup.find("div", attrs={"role": "main"})
    if body is None:
        sys.exit('error: could not find <div role="main"> in the HTML page')

    strip_chrome(body)
    # Replace code blocks and option tables with placeholders so pandoc never
    # sees them; both are spliced back from `replacements` after conversion.
    replacements = {**replace_code_blocks(body), **replace_tables(body)}

    md = run_pandoc(body.decode_contents())
    md = re.sub(r"</?div[^>]*>\n?", "", md)  # leftover section wrapper divs
    md = re.sub(r"\n{3,}", "\n\n", md)
    for key, rendered in replacements.items():
        md = md.replace(key, rendered)

    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(md.rstrip("\n") + "\n")  # exactly one trailing newline


if __name__ == "__main__":
    main()
