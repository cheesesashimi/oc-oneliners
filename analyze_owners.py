#!/usr/bin/env python3

# Used primarily to evalute OpenShift repositories that have many OWNERS files throughout the repository.

from collections import defaultdict

import os
import sys
import yaml

def load_file(filename):
    try:
        with open(filename, "r") as loaded_file:
            return list(yaml.safe_load_all(loaded_file))[0]
    except FileNotFoundError:
        return {}

def load_top_level_owners_file(filename):
    loaded = load_file(filename)
    if loaded == {}:
        return {}

    if not loaded.get("filters"):
        return loaded

    approvers = set()
    reviewers = set()
    for filt in loaded["filters"]:
        if filt.get("approvers"):
            approvers = approvers.union(set(filt["approvers"]))

        if filt.get("reviewers"):
            reviewers = reviewers.union(set(filt["reviewers"]))

    return {
        "approvers": list(approvers),
        "reviewers": list(reviewers),
    }

# Find all the OWNERS files in a given repository, excluding the .git and
# vendor directories for speed
def find_owner_files(root_path):
    exclude = set(("vendor", ".git"))

    for root, dirs, files in os.walk(root_path, topdown=True):
        dirs[:] = [d for d in dirs if d not in exclude]
        for name in files:
            if name == "OWNERS":
                yield os.path.join(root, name)

def load_owners_aliases(root_path):
    loaded = load_file(os.path.join(root_path, "OWNERS_ALIASES"))
    if not loaded.get("aliases"):
        return {}

    return {alias: set(team) for alias, team in loaded["aliases"].items()}

def load_owners_files(root_path):
    owners_files = {}
    for filename in find_owner_files(root_path):
        if filename != os.path.join(root_path, "OWNERS"):
            owners_files[filename] = load_file(filename)
    return owners_files

def load_all_files(root_path):
    return {
        "owners_files": load_owners_files(root_path),
        "top_level_owners_file": load_top_level_owners_file(os.path.join(root_path, "OWNERS")),
        "owners_aliases": load_owners_aliases(root_path),
    }

def lookup_known_aliases(approvers, reviewers, loaded_files):
    owners_aliases = loaded_files["owners_aliases"]
    found_aliases = set()
    if loaded_files["top_level_owners_file"].get("approvers"):
        found_aliases = found_aliases.union(set(loaded_files["top_level_owners_file"]["approvers"]))

    if loaded_files["top_level_owners_file"].get("reviewers"):
        found_aliases = found_aliases.union(set(loaded_files["top_level_owners_file"]["reviewers"]))

    found_aliases = found_aliases.union(set(approvers.keys())).union(set(reviewers.keys()))
    return {alias: sorted(list(owners_aliases[alias]))
            for alias in found_aliases
            if alias in owners_aliases}

approvers_by_file = defaultdict(list)
reviewers_by_file = defaultdict(list)

loaded_files = load_all_files(sys.argv[1])

for owners_file, doc in loaded_files["owners_files"].items():
    print(owners_file)
    if doc.get("approvers"):
        for approver in doc["approvers"]:
            approvers_by_file[approver].append(owners_file)

    if doc.get("reviewers"):
        for reviewer in doc["reviewers"]:
            reviewers_by_file[reviewer].append(owners_file)

out = {
    "approvers_by_file": dict(approvers_by_file),
    "reviewers_by_file": dict(reviewers_by_file),
    "top_level_owners": loaded_files["top_level_owners_file"],
}

if loaded_files["owners_aliases"] != {}:
    out["top_level_owners"] = lookup_known_aliases(approvers_by_file, reviewers_by_file, loaded_files)

print(yaml.safe_dump(out))
