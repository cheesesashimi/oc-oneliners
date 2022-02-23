#!/usr/bin/env python3

from collections import defaultdict

import os
import sys
import yaml

def load_file(filename):
    with open(filename, "r") as loaded_file:
        return list(yaml.safe_load_all(loaded_file))[0]

# Find all the OWNERS files in a given repository, excluding the .git and
# vendor directories for speed
def find_owner_files(root_path):
    exclude = set(("vendor", ".git"))

    for root, dirs, files in os.walk(root_path, topdown=True):
        dirs[:] = [d for d in dirs if d not in exclude]
        for name in files:
            if name == "OWNERS":
                yield os.path.join(root, name)

def load_all_files(root_path):
    return {
        "owners_files": {filename: load_file(filename)
                         for filename in find_owner_files(root_path)
                         if filename != os.path.join(root_path, "OWNERS")},
        "top_level_owners_file": load_file(os.path.join(root_path, "OWNERS")),
        "owners_aliases": {alias: set(team)
                           for alias, team in load_file(os.path.join(root_path, "OWNERS_ALIASES"))["aliases"].items()}
    }

def lookup_known_aliases(approvers, reviewers, loaded_files):
    owners_aliases = loaded_files["owners_aliases"]
    top_level_aliases = set(loaded_files["top_level_owners_file"]["approvers"]).union(loaded_files["top_level_owners_file"]["reviewers"])
    found_aliases = set(approvers.keys()).union(set(reviewers.keys())).union(top_level_aliases)
    return {alias: sorted(list(owners_aliases[alias]))
            for alias in found_aliases
            if alias in owners_aliases}

approvers_by_file = defaultdict(list)
reviewers_by_file = defaultdict(list)

loaded_files = load_all_files(sys.argv[1])

for owners_file, doc in loaded_files["owners_files"].items():
    if doc.get("approvers"):
        for approver in doc["approvers"]:
            approvers_by_file[approver].append(owners_file)

    if doc.get("reviewers"):
        for reviewer in doc["reviewers"]:
            reviewers_by_file[reviewer].append(owners_file)

out = {
    "approvers_by_file": dict(approvers_by_file),
    "reviewers_by_file": dict(reviewers_by_file),
    "reviewers_by_alias": lookup_known_aliases(approvers_by_file, reviewers_by_file, loaded_files),
    "top_level_owners": loaded_files["top_level_owners_file"],
}

print(yaml.safe_dump(out))
