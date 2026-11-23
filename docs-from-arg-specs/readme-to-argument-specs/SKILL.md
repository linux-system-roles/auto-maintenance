---
name: readme-to-argument-specs
description: >-
  Convert a linux-system-roles hand-written README.md into a native
  meta/argument_specs.yml (antsibull semantic-markup fields) plus a
  meta/extra_specs.yml for the keys the released ansible-lint schema rejects, then
  generate README.md and a self-contained README.html from them with the
  build-docs tox environment. Use when asked to "generate role docs from
  argument_specs", "convert the README to argument_specs", document a role's
  returned variables, add examples / notes / attributes to a role's
  argument_specs, or fix escaped backticks/links in a generated role README.
---

# README.md → meta/argument_specs.yml

Convert a role's hand-written `README.md` into native antsibull fields in `meta/argument_specs.yml` (plus `meta/extra_specs.yml` for `notes:`/`return:`), then render `README.md` and a self-contained `README.html` with `tox -e build-docs`.
`README.md` is canonical; the build never emits `README.txt`/`README.rst` (RST is only an internal Sphinx intermediate).

Complete template examples are available in the linux-system-roles/template role:
- [meta/argument_specs.yml](https://github.com/linux-system-roles/template/blob/main/meta/argument_specs.yml) — template with placeholders and inline guidance
- [meta/extra_specs.yml](https://github.com/linux-system-roles/template/blob/main/meta/extra_specs.yml) — template for notes and return variables

Copy and adapt them rather than starting from scratch.

## Core principles

- **Native fields, two exceptions.**
  Content lives in `argument_specs.yml` native fields (`short_description`, `description`, `author`, `attributes`, `options`, `examples`).
  The released ansible-lint schema rejects `notes:` and `return:` under an entry point, so those two live in `meta/extra_specs.yml` and are merged in at build time (see "The extra_specs.yml split").
- **Lose no content — but not errors.**
  Preserve every variable, default, choice, warning, requirement, caveat, and example; if something no longer applies, say so rather than dropping it.
  But when the source contradicts the code (a wrong variable name, a stale default), document the code's reality and note the correction — preserve facts, not mistakes.
- **Never hand-edit generated files.**
  Edit `argument_specs.yml`/`extra_specs.yml` and rebuild.
  `README.html` is one self-contained file; no `sphinx_html/` tree or `_static/` assets are committed.
- **Never copy build scripts into the role.**
  `tox -e build-docs` (from tox-lsr) fetches and runs them.
- **Work locally.**
  Do not commit or push unless the user explicitly asks.

## Where content goes (entry point `main`)

| Field | Lives in | Renders as | Put here |
|---|---|---|---|
| `short_description` | argument_specs.yml | page subtitle | one-line role summary |
| `description` | argument_specs.yml | **Synopsis** | the summary **and all narrative/operational prose**: providers, requirements, warnings, compatibility, limitations, caveats. One list item = one bullet. |
| `author` | argument_specs.yml | Authors | list of `Name (@githubhandle)` (from `meta/main.yml`) |
| `attributes` | argument_specs.yml | Attributes table | see "Attributes" below |
| `options` | argument_specs.yml | Parameters table | every role variable: `type`, `default`, `choices`, `description`, nested sub-`options` |
| `examples` | argument_specs.yml | Examples | an `examples:` literal block of full plays (`name`, `hosts`, `vars`, `roles`) |
| `notes` | **extra_specs.yml** | **Notes** | **only** low-level internals (why a variable is not declared, how a fact-dependent default resolves). Omit when there are none. |
| `return` | **extra_specs.yml** | **Return Variables** table | every variable the role sets: `type`, `elements` (for lists), `returned`, `sample`, and `contains` for dicts |

Include a field only when it carries real content; omit empty sections rather than emitting filler.
`short_description`, `description`, and `options` are effectively always present; the rest are optional.
License has no field — it stays in `LICENSE`/`meta/main.yml` and is intentionally not a generated README section.
Convert only `README.md`; for a sibling doc (e.g. `README-ostree.md`) fold its user-facing *support* facts into the Synopsis but leave its developer/build instructions — and the pointer to it — alone.

**Source of truth for type/default.**
The existing `argument_specs.yml` option tree and `defaults/main.yml` are authoritative — they drive runtime validation.
The README's prose type words ("int", "dict", "string") are only descriptive; do not let them override the declared `type`/`default` (e.g. keep `raw`/`list`/`{}` if that is what the spec and defaults say).

**Attributes.**
Name the OS attribute **`platforms`** (not `platform`) with the OSes under `details:`; antsibull special-cases a `platform` attribute and drops the support badge.
Derive the supported OSes from `galaxy_tags` in `meta/main.yml` - the `galaxy_info` `platforms:` list is deprecated and often stale - e.g. tags `el7`/`el8`/`el9`/`el10`/`fedora` mean EL 7, 8, 9, 10 and Fedora.
**Verify that the OSes from `galaxy_tags` match what the README documents.** If the README mentions different or additional OSes, reconcile the discrepancy: update either `galaxy_tags` or the README to match, or ask the role maintainers which is the source of truth. Do not silently omit supported systems.
Add `architectures` from the README's "Supported architectures" section, and `check_mode`/`idempotent` from known role behavior or tests.
Every attribute needs a `support:` value — omit any attribute you cannot determine rather than inventing one.

## The extra_specs.yml split

`notes:` and `return:` render as the "Notes" section and "Return Variables" table, but the released ansible-lint role-arg-spec schema rejects both under an entry point (confirmed on 24.2 / 24.12 / 25.1 / 25.9 / 26.10; allowed keys are attributes, author, description, examples, options, seealso, short_description, version_added).
So put them as top-level keys in `meta/extra_specs.yml`; at build time `merge_extra_specs.py` injects them into a throwaway copy of `argument_specs.yml`'s `main` entry point, leaving the committed files lint-clean and untouched.

- `O()` cross-refs to top-level options resolve from here, because the content is merged into `main`.
- A role with neither notes nor returned variables needs no `extra_specs.yml`.
- The released antsibull-docs does not render `return:`; the toolchain uses a patched fork (see "Build and verify").

## Preserve content, improve prose

Inventory the source `README.md` before converting — every variable with its type/default/choices, and every warning, requirement, compatibility note, limitation, caveat, and example.
After building, reconcile the generated `README.md` against that inventory (Workflow step 6); nothing may silently disappear.

Tighten the prose as you map it — same meaning, clearer delivery:

- Concise: cut filler ("in order to" → "to"); one idea per sentence.
- Unambiguous: name the exact variable/value/file, not "it"/"this"/"the above".
- Active voice, present tense: "the role installs", not "X is installed by the role" or "the role will have installed".
- Consistent terms: one name per thing throughout.
- One sentence per source line in folded (`>`) scalars — folding rejoins them, so rendering is unchanged but diffs stay sentence-granular.

Rephrasing for clarity is encouraged; changing meaning or omitting a fact is not.

## Semantic markup (NOT Markdown)

antsibull descriptions are not Markdown: literal backticks and `[text](url)` pass through and pandoc escapes them (`\``, `\[`, `\]`) — the exact defect to eliminate.
Convert everything to macros:

- `L(text,url)` — links.
- `V(value)` — literal values (`true`/`false`, choices, numbers, IPs, type values, …).
- `C(code)` — commands, paths, package/module names, config tokens, and sub-option names used as identifiers.
- `O(name)` — references to **top-level** options defined in this spec (nested paths are error-prone and flatten anyway; use `C()` for sub-options).
- `B(text)` — bold.

The same token varies by context: `V(bond)` (a value) vs `C(bond)` (a dict) vs `O(network_connections)` (an option).
Never use `O()` for something not declared as an option — it becomes an unresolved cross-reference; use `C()`.

### Gotchas

- **Colon-space in a scalar.**
  A description containing `: ` — e.g. `C(value: "on")` — breaks a plain YAML scalar (`mapping values are not allowed here`).
  Use a block scalar (`>`/`|`) or quote the string.
- **Parens inside `C()`.**
  `C(foo())` breaks (the first `)` closes the macro) and escaping leaks backslashes; reword to "the `C(foo)` function".
- **Possessive after a span.**
  `C(ethtool)'s` makes pandoc emit a wrong-way curly quote; reword to avoid it.
- **Punctuation-only span glued to text.**
  `C(-)-separated` renders as `` `-`-separated ``; reword ("hyphen-separated").
- **Option cross-refs flatten to plain text** in `README.md` (a flat file has no anchors), so `O()` differs from `C()` only by being bold — another reason to reserve `O()` for top-level options.
- **Large lists of undescribed values** (e.g. ~90 boolean `ethtool` features): point the parent `description` at the upstream tool and state they are all boolean toggles; do not describe each.
- **ASCII only.**
  The pipeline keeps straight quotes and `--`; do not introduce en-dashes or curly quotes — the linters reject them.

## Build and verify

Run `tox -e build-docs` from the role root (tox-lsr must be installed — see its README; the first run needs network to fetch the generator scripts and build a venv).
It merges `extra_specs.yml`, runs antsibull-docs → Sphinx → one self-contained `README.html` and pandoc → `README.md`, and rewrites the title to the short role name (`# <role> role -- ...`, via `LSR_README_ROLE_NAME_STYLE=short`).
It uses a patched antsibull-docs fork for `return:` rendering until that ships upstream.
After building, delete any leftover hidden `.README.html` (from the previous docs mechanism).

Verification checklist (from the role root):

```bash
python3 -c "import yaml; yaml.safe_load(open('meta/argument_specs.yml')); print('argspec OK')"
# only if the role has notes and/or returned variables:
python3 -c "import yaml; d=yaml.safe_load(open('meta/extra_specs.yml')); assert d.keys() & {'notes','return'}; print('extra_specs OK')"
grep -nP '[^\x00-\x7F]' README.md && echo 'NON-ASCII (bug)' || echo 'ASCII OK'
grep -cP '\\\`' README.md    # -> 0  escaped backticks (plain `code` spans are expected and fine)
grep -cP '\\\[' README.md    # -> 0  escaped link brackets
grep -c '<div' README.md     # -> 0
grep -oE '^### (Synopsis|Parameters|Attributes|Notes|Examples|Authors|Return Variables)' README.md
```

`Synopsis` and `Parameters` are always present; the rest appear only if you populated them — confirm the ones you intended are there and that an omitted one (e.g. `Notes`) did not leak back.
These greps must match *escaped* markup, not legitimate markup.
A plain `grep -c` for a backtick or bracket counts every real code span and link, so it is **not** 0 on a correct README; the `\\`-escaped PCRE forms above match only the pandoc-escaped sequences.

Confirm the tables survive Galaxy's sanitizer:

```bash
python3 - <<'PY'
import markdown, nh3
tags={"h1","h2","h3","h4","h5","h6","b","i","strong","em","tt","p","br","span",
      "div","blockquote","code","pre","hr","ul","ol","li","dd","dt","img","a",
      "sub","sup","table","thead","th","tr","td"}
out=nh3.clean(markdown.markdown(open("README.md").read(),extensions=["extra"]),
              tags=tags, attributes={"*":{"id"},"img":{"src","alt","title"},
              "a":{"href","alt","title"}}, strip_comments=True)
print("tables:",out.count("<table"),"| embedded div:",out.count("<div"))
PY
# embedded div must be 0; tables = Parameters + one per populated Attributes / Return Variables
# section (so 2-3), not a fixed number.
```

## Workflow

1. Read `README.md` in full and inventory it (sections; every variable's type/default/choices; every warning/requirement/caveat; every example; every backtick/link). This inventory is your no-loss checklist for step 6.
2. Read `meta/argument_specs.yml` (the option tree) and `meta/main.yml` (author, `galaxy_tags` for platforms, license).
3. Map content into the fields per the table: prose → `description`; variables → `options` (keep the existing `type`/`default` — see "Source of truth"); playbooks → `examples` (~8-10 representative plays, secrets → vault refs); authors/platforms/architectures → `author`/`attributes`; low-level internals → `notes` and returned variables → `return:`, both in `extra_specs.yml`.
4. Tighten the prose and convert all inline markup to `C`/`V`/`O`/`L`/`B`, watching the gotchas.
5. Run `tox -e build-docs`, delete any `.README.html`, and run the full verification. Rebuild until clean.
6. Reconcile the generated `README.md` against the step-1 inventory; anything missing is a conversion bug — fix the spec and rebuild.
7. Do not commit or push unless explicitly asked.

To enable the automated freshness check (separate from converting the docs, and optional — skip if you are only converting): add the role to the **`arg_specs_docs`** group in the `linux-system-roles/.github` `inventory/inventory.yml` and run its `playbooks/update_files.yml` for that role.
That distributes the `check-docs-updated` workflow (which reruns `tox -e build-docs` and fails a PR when the committed README is stale) and retires the old pandoc docs workflow; you need not know its internals.
