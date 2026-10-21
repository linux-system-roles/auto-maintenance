# docs-from-arg-specs

Generate a role's `README.md` and `README.html` from its `meta/argument_specs.yml` (and optional `meta/set_vars_specs.yml`), so the docs are authored once in native [antsibull-docs][antsibull] fields and rendered from there.

Run `build_docs.sh` against a role directory — locally, or from a tox env, or git hook.
`README.md` is the canonical output; `README.html` is a single, self-contained styled preview.

## Files

| File | Purpose |
|---|---|
| `build_docs.sh` | Orchestrator — builds `README.md` + `README.html` for a role. Run this. |
| `merge_set_vars.py` | Folds `meta/set_vars_specs.yml`'s `return:` into a temporary copy of `argument_specs.yml` at build time. |
| `html_to_singlefile.py` | Collapses the Sphinx HTML site into one self-contained `README.html`. |
| `html_to_md.py` | Converts the Sphinx HTML page into `README.md` (pandoc + Markdown pipe tables). |

Keep the four files together; `build_docs.sh` finds the helpers next to itself.

## Usage

```
build_docs.sh [ROLE_DIR]      # ROLE_DIR defaults to the current directory
```

Writes `README.md` and `README.html` into the role directory.

Requirements: `python3`, `git`, and network access on the first run.
`build_docs.sh` installs the toolchain into a reusable venv: `antsibull-docs` from a patched GitHub fork (cloned with `git`; see the note below), and `sphinx`, `ansible-pygments`, `sphinx-ansible-theme`, and `pandoc` (via `pypandoc-binary`) from PyPI.
Set `ANTSIBULL_RV_VENV` to change the venv location; delete it to refresh.

> The venv uses a patched antsibull-docs fork (`git+https://github.com/spetrosi/antsibull-docs@role-return-values`) that adds rendering of a role's `return:` key (the "Return Variables" table), which released antsibull-docs lacks; drop it once that support ships upstream.

## How it works

```
merge_set_vars.py    (restore return: into a temp argument_specs.yml)
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

- `meta/argument_specs.yml` — role docs in native antsibull fields (`short_description`, `description`, `author`, `notes`, `attributes`, `options`, `examples`).
- `meta/set_vars_specs.yml` *(optional)* — variables the role returns, under a top-level `return:` key (`type`, `returned`, `sample`, `contains`).
  It lives separately because the released ansible-lint schema rejects a `return:` key in `argument_specs.yml`; a `notes` entry there points at it, and `merge_set_vars.py` folds it back in (and drops that note) at build time.

## Running the helpers directly

```bash
merge_set_vars.py ARGUMENT_SPECS.yml SET_VARS_SPECS.yml DEST.yml
html_to_singlefile.py [--drop-scripts] [--standalone] [--drop-fonts] IN.html OUT.html
html_to_md.py IN.html OUT.md
```

[antsibull]: https://github.com/ansible-community/antsibull-docs
