#!/usr/bin/python3

import sys
import io
import re
import yaml


COLLECTION_RELEASE = "collection_release.yml"
SPECFILE_IN = sys.argv[1]
SPECFILE_OUT = sys.argv[2]

BEGIN_SOURCES_MARKER = "# BEGIN AUTOGENERATED SOURCES"
END_SOURCES_MARKER = "# END AUTOGENERATED SOURCES"

BEGIN_SETUP_MARKER = "# BEGIN AUTOGENERATED SETUP"
END_SETUP_MARKER = "# END AUTOGENERATED SETUP"

BEGIN_SETUP_TMPL = "%setup -q "
END_SETUP_TMPL = " -n %{getarchivedir 0}"


class Replacement:
    """Class describing a replacement of lines between markers in a file"""

    def __init__(self, begin_marker, end_marker, generate):
        self.begin_marker = begin_marker
        self.end_marker = end_marker
        self.generate = generate
        self.throwaway = False
        self.marker_seen = False

    def process_line(self, line):
        # did we change the input line? If not, we are merely returning it.
        changed = False
        of = io.StringIO()
        if not self.throwaway:
            of.write(line)
            if line.strip() == self.begin_marker:
                if self.marker_seen:
                    sys.exit("Duplicate replacement section")
                changed = True
                self.generate(of)
                self.throwaway = True
                self.marker_seen = True
            elif line.strip() == self.end_marker:
                sys.exit("End marker '{}' without begin marker".format(self.end_marker))
        else:
            if line.strip() == self.end_marker:
                self.throwaway = False
                of.write(line)
            elif line.strip() == self.begin_marker:
                sys.exit("Duplicate begin marker: {}".format(self.begin_marker))
            else:
                # we discarded the input line
                changed = True

        return (changed, of.getvalue())

    def inside(self):
        """Are we currently inside the replacement block?"""
        return self.throwaway

    def after(self):
        """Have we been inside the replacement block?"""
        return self.marker_seen and not self.throwaway


def ref_is_commit(ref):
    if re.match(r"[0-9a-f]{5,40}$", ref):
        # is a SHA-1 commit id
        return True
    elif re.search(r"[0-9]+[.][0-9]+[.][0-9]+", ref):
        # is a tag
        # search() and not match() because there could be something in front
        # of the semantic version number, like literal "v" - we have tags looking
        # both like "v1.2.0" and like "1.2.0"
        return False
    else:
        sys.exit(f"unknown format of reference '{ref}': neither commit nor semver tag")


def generate_sources(output):
    k = list(rolesbysourcenum.keys())
    k.sort()

    for i in k:
        r = rolesbysourcenum[i]
        org = roles[r].get("org")
        repo = roles[r].get("repo")
        ref = roles[r]["ref"]
        if org:
            # If we support other hosting service than Github, the format
            # of collection_release.yml will have to change a bit.
            output.write(f"%global forgeorg{i} https://github.com/{org}\n")
        if repo:
            output.write(f"%global repo{i} {repo}\n")
        output.write(f"%global rolename{i} {r}\n")
        if ref_is_commit(ref):
            output.write(f"%defcommit {i} {ref}\n\n")
        else:
            output.write(f"%deftag {i} {ref}\n\n")
    for i in k:
        output.write(f"Source{i}: %{{archiveurl{i}}}\n")


def generate_setup(output):
    k = list(rolesbysourcenum.keys())
    k.sort()

    output.write(
        BEGIN_SETUP_TMPL + " ".join(f"-a{i}" for i in k) + END_SETUP_TMPL + "\n"
    )


with open(COLLECTION_RELEASE, "r") as cf:
    roles = yaml.safe_load(cf)
    for rolename, roleinfo in roles.items():
        print(roleinfo)
    rolesbysourcenum = {
        roleinfo["sourcenum"]: rolename for rolename, roleinfo in roles.items()
    }


sources_replacement = Replacement(
    BEGIN_SOURCES_MARKER, END_SOURCES_MARKER, generate_sources
)
setup_replacement = Replacement(BEGIN_SETUP_MARKER, END_SETUP_MARKER, generate_setup)

f = open(SPECFILE_IN, "r")
of = open(SPECFILE_OUT, "w")

for line in f:
    changed_sources, new_line = sources_replacement.process_line(line)
    changed_setup, new_new_line = setup_replacement.process_line(new_line)
    if changed_sources and changed_setup:
        sys.exit(
            "Begin marker {} in the output of sources replacement".format(
                setup_replacement.begin_marker
            )
        )
    of.write(new_new_line)

for i in (sources_replacement, setup_replacement):
    if i.inside():
        sys.exit("Missing end marker '{}'".format(i.end_marker))
    elif not i.after():
        sys.exit("Missing begin marker '{}'".format(i.begin_marker))
