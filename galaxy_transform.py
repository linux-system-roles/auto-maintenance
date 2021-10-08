#!/usr/bin/python3

# Changes namespace, name, and version in Galaxy metadata.
# Useful for releasing to Automation Hub, where Collections live
# in namespaces separated from Ansible Galaxy.

import sys
from ruamel.yaml import YAML

filepath = "galaxy.yml"

buf = open(filepath).read()

yaml = YAML(typ="rt")
yaml.default_flow_style = False
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)

code = yaml.load(buf)

code["namespace"] = sys.argv[1]
code["name"] = sys.argv[2]
code["version"] = sys.argv[3]
code["description"] = sys.argv[4]
if len(sys.argv) > 5:
    code["repository"] = sys.argv[5]
    code["documentation"] = sys.argv[6]
    code["homepage"] = sys.argv[7]
    code["issues"] = sys.argv[8]
yaml.dump(code, sys.stdout)
