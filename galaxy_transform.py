#!/usr/bin/python3

# Changes namespace, name, and version in Galaxy metadata.
# Useful for releasing to Automation Hub, where Collections live
# in namespaces separated from Ansible Galaxy.

import sys
from ruamel.yaml import YAML

filepath = "galaxy.yml"

buf = open(filepath).read()

yaml = YAML()
code = yaml.load(buf)

code["namespace"] = sys.argv[1]
code["name"] = sys.argv[2]
code["version"] = sys.argv[3]
yaml.dump(code, sys.stdout)
