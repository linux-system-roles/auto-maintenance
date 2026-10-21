#!/usr/bin/env bash
# Build README.md and README.html for a role from meta/argument_specs.yml.
# What this does and why (pipeline, the fork, why a collection): see README.md.
#
# Usage: build_docs.sh [ROLE_DIR]   # ROLE_DIR defaults to the current directory

set -euo pipefail

# Toolchain venv, created once and reused (override with ANTSIBULL_RV_VENV, delete
# to refresh). First run needs network.
# Pinned commit on the role-return-values branch for reproducible installs.
ANTSIBULL_RV_SPEC='antsibull-docs @ git+https://github.com/spetrosi/antsibull-docs@dcef106ec0e3ad06b14f63714e48ad8c4506c7ff'
ANTSIBULL_RV_VENV="${ANTSIBULL_RV_VENV:-${XDG_CACHE_HOME:-$HOME/.cache}/lsr-antsibull-docs}"
# (Re)install if antsibull-docs or the pandoc symlink is missing.
if [ ! -x "$ANTSIBULL_RV_VENV/bin/antsibull-docs" ] || [ ! -e "$ANTSIBULL_RV_VENV/bin/pandoc" ]; then
    echo "Installing patched antsibull-docs and pandoc into $ANTSIBULL_RV_VENV ..." >&2
    python3 -m venv "$ANTSIBULL_RV_VENV"
    "$ANTSIBULL_RV_VENV/bin/pip" install --quiet --upgrade pip
    "$ANTSIBULL_RV_VENV/bin/pip" install --quiet \
        "$ANTSIBULL_RV_SPEC" ansible-pygments sphinx sphinx-ansible-theme pypandoc-binary
    # pandoc lives inside the pypandoc package; link it onto the venv bin (on PATH).
    ln -sf "$("$ANTSIBULL_RV_VENV/bin/python" -c 'import pypandoc; print(pypandoc.get_pandoc_path())')" \
        "$ANTSIBULL_RV_VENV/bin/pandoc"
fi
PATH="$ANTSIBULL_RV_VENV/bin:$PATH"

for tool in antsibull-docs sphinx-build pandoc; do
    command -v "$tool" >/dev/null 2>&1 || { echo "error: $tool not found on PATH" >&2; exit 1; }
done

# SCRIPT_DIR: where the helpers live. ROLE_DIR: the role to build (arg, default CWD).
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROLE_DIR="$(cd -- "${1:-$PWD}" && pwd)"
ROLE_NAME="$(basename "$ROLE_DIR")"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Mirror the role into a temporary collection with symlinks (role tree untouched),
# regenerating only meta/argument_specs.yml below.
COLL="$WORK/collections/ansible_collections/fedora/linux_system_roles"
ROLE_LINK="$COLL/roles/$ROLE_NAME"
mkdir -p "$ROLE_LINK/meta"
# symlink every top-level entry except meta/ (handled below)
for item in "$ROLE_DIR"/*; do
    name="$(basename "$item")"
    [ "$name" = "meta" ] && continue
    ln -s "$item" "$ROLE_LINK/$name"
done
# symlink meta/ entries except argument_specs.yml (generated below)
for item in "$ROLE_DIR"/meta/*; do
    name="$(basename "$item")"
    [ "$name" = "argument_specs.yml" ] && continue
    ln -s "$item" "$ROLE_LINK/meta/$name"
done
# If meta/set_vars_specs.yml exists, merge its return: into the spec; else use the
# spec as-is (set_vars_specs.yml is optional).
if [ -f "$ROLE_DIR/meta/set_vars_specs.yml" ]; then
    python3 "$SCRIPT_DIR/merge_set_vars.py" \
        "$ROLE_DIR/meta/argument_specs.yml" \
        "$ROLE_DIR/meta/set_vars_specs.yml" \
        "$ROLE_LINK/meta/argument_specs.yml"
else
    ln -s "$ROLE_DIR/meta/argument_specs.yml" "$ROLE_LINK/meta/argument_specs.yml"
fi
# version is required but unused here; leave it empty.
cat > "$COLL/galaxy.yml" <<EOF
namespace: fedora
name: linux_system_roles
version: ""
readme: README.md
authors: [Linux System Roles]
EOF
echo "# linux_system_roles" > "$COLL/README.md"
export ANSIBLE_COLLECTIONS_PATH="$WORK/collections"

# antsibull writes the config it needs (conf.py, antsibull-docs.cfg).
mkdir -p "$WORK/site"
antsibull-docs sphinx-init --use-current --squash-hierarchy \
    --dest-dir "$WORK/site" fedora.linux_system_roles

cd "$WORK/site"

# 1. antsibull: spec -> RST (an intermediate for Sphinx; not shipped).
chmod og-w rst   # antsibull-docs requires this dir not be group/other-writable
antsibull-docs --config-file antsibull-docs.cfg collection \
    --cleanup everything --use-current --squash-hierarchy \
    --dest-dir rst fedora.linux_system_roles

# Don't ship the RST source or the "Show Source" link.
printf '\nhtml_copy_source = False\nhtml_show_sourcelink = False\n' >> conf.py

# 2. Sphinx renders the RST to the styled HTML site.
sphinx-build -M html rst build -q -c .

# 3. html_to_singlefile.py -> one self-contained README.html.
python3 "$SCRIPT_DIR/html_to_singlefile.py" --drop-scripts --standalone --drop-fonts \
    "build/html/${ROLE_NAME}_role.html" "$ROLE_DIR/README.html"

# 4. html_to_md.py -> README.md.
python3 "$SCRIPT_DIR/html_to_md.py" \
    "build/html/${ROLE_NAME}_role.html" "$ROLE_DIR/README.md"

echo "MD  : $ROLE_DIR/README.md"
echo "HTML: $ROLE_DIR/README.html (single self-contained file)"
