# docs-from-arg-specs

Generate a role's `README.md` and `README.html` from its `meta/argument_specs.yml` (and optional `meta/extra_specs.yml`), so the docs are authored once in native [antsibull-docs][antsibull] fields and rendered from there.

Run `build_docs.sh` against a role directory — locally, or from a tox env, or git hook.
`README.md` is the canonical output; `README.html` is a single, self-contained styled preview.

## Files

| File | Purpose |
|---|---|
| `build_docs.sh` | Orchestrator — builds `README.md` + `README.html` for a role. Run this. |
| `merge_extra_specs.py` | Folds `meta/extra_specs.yml`'s `notes:` and `return:` into a temporary copy of `argument_specs.yml` at build time. |
| `html_to_singlefile.py` | Collapses the Sphinx HTML site into one self-contained `README.html`. |
| `html_to_md.py` | Converts the Sphinx HTML page into `README.md` (pandoc + Markdown pipe tables). |
| `set_role_title.py` | Rewrites the role name in the rendered HTML title (used when `LSR_README_ROLE_NAME_STYLE=short`; see Usage). |

Keep the five files together; `build_docs.sh` finds the helpers next to itself.

## Usage

```
build_docs.sh [ROLE_DIR]      # ROLE_DIR defaults to the current directory
```

Writes `README.md` and `README.html` into the role directory.

By default the title keeps the collection FQCN that antsibull emits
(`# fedora.linux_system_roles.bootloader role -- ...`). Set
`LSR_README_ROLE_NAME_STYLE=short` to use the bare role name instead
(`# bootloader role -- ...`), which is namespace-agnostic and works for any role:

```
LSR_README_ROLE_NAME_STYLE=short build_docs.sh [ROLE_DIR]
```

Requirements: `python3` and network access (on first pip install).

Install the toolchain once with `pip install -r requirements.txt` (into a venv if working standalone).
Then run `build_docs.sh` — the script checks that `antsibull-docs` and `sphinx-build` are on `PATH`, resolves `pandoc` from the installed `pypandoc-binary` package, and exits with a clear error if they're missing.

The toolchain uses a patched `antsibull-docs` fork (pinned in `requirements.txt`) that adds rendering of a role's `return:` key (the "Return Variables" table), which released antsibull-docs lacks; the pin can be dropped once that support ships upstream.

## How it works

```
merge_extra_specs.py (restore notes: and return: into a temp argument_specs.yml)
      │
antsibull-docs       (argument_specs.yml -> RST)
      │
sphinx-build         (RST -> styled HTML site)
      │
      ├── html_to_singlefile.py  -> README.html
      └── html_to_md.py (pandoc)  -> README.md
```

`ansible-doc` only prints a role's `argument_specs` as plain text or JSON to the terminal — it has no HTML or Markdown output — so it cannot produce a README.
antsibull-docs is the generator behind docs.ansible.com: it renders the spec to RST/HTML with Ansible semantic markup (`C()`, `V()`, `O()`, `L()`, `B()`) resolved to formatting and cross-reference links, and with structured Parameters/Attributes/Return-Variables tables (nested options indented).
antsibull-docs operates on collections, so `build_docs.sh` mirrors the role into a temporary `fedora.linux_system_roles` collection and renders that, regenerating only `meta/argument_specs.yml`.

## Role inputs

- `meta/argument_specs.yml` — role docs in native antsibull fields (`short_description`, `description`, `author`, `attributes`, `options`, `examples`).
- `meta/extra_specs.yml` *(optional)* — documentation the released ansible-lint schema rejects in `argument_specs.yml`: a top-level `notes:` key (the role's "Notes" section) and a top-level `return:` key describing returned variables (`type`, `returned`, `sample`, `contains`).
  It lives separately because the released ansible-lint schema rejects `notes:` and `return:` in `argument_specs.yml`; `merge_extra_specs.py` folds them back in at build time.

## Running the helpers directly

```bash
merge_extra_specs.py ARGUMENT_SPECS.yml EXTRA_SPECS.yml DEST.yml
html_to_singlefile.py [--drop-scripts] [--standalone] [--drop-fonts] IN.html OUT.html
html_to_md.py IN.html OUT.md
set_role_title.py HTML_FILE ROLE_NAME
```

[antsibull]: https://github.com/ansible-community/antsibull-docs
