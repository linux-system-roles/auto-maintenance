#!/usr/bin/env python3
"""Merge meta/extra_specs.yml's notes: and return: into a copy of argument_specs.yml.

extra_specs.yml holds documentation that does not yet fit the released
ansible-lint role-arg-spec schema (the native notes: and return: keys). Keeping
it in a separate file lets argument_specs.yml stay lint-clean; this script folds
the content back into a throwaway copy of argument_specs.yml at build time. The
committed files are untouched. See README.md for details.

Usage: merge_extra_specs.py ARGUMENT_SPECS EXTRA_SPECS DEST
"""

import sys

import yaml

# Keys in extra_specs.yml that are injected into the role's main entry point.
MERGE_KEYS = ("notes", "return")


def main(argv):
    if len(argv) != 4:
        sys.exit(f"usage: {argv[0]} ARGUMENT_SPECS EXTRA_SPECS DEST")
    argument_specs_path, extra_specs_path, dest_path = argv[1:]

    with open(argument_specs_path, encoding="utf-8") as specs_file:
        specs = yaml.safe_load(specs_file)
    with open(extra_specs_path, encoding="utf-8") as extra_file:
        extra = yaml.safe_load(extra_file)

    entry_points = specs["argument_specs"]
    if "main" not in entry_points:
        sys.exit(
            f"{argv[0]}: argument_specs has no 'main' entry point "
            f"(found: {', '.join(entry_points) or 'none'})"
        )
    main_entry = entry_points["main"]
    for key in MERGE_KEYS:
        if key in extra:
            main_entry[key] = extra[key]

    with open(dest_path, "w", encoding="utf-8") as dest_file:
        yaml.safe_dump(
            specs,
            dest_file,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
            width=4096,
        )


if __name__ == "__main__":
    main(sys.argv)
