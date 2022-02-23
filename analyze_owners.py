#!/usr/bin/env python3

import os
import sys
import yaml

def read_owners_file(filename):
    with open(filename, "r") as owners_file:
        return list(yaml.safe_load_all(owners_file))

def find_owner_files(root_path):
    exclude = set(("vendor", ".git"))

    for root, dirs, files in os.walk(root_path, topdown=True):
        dirs[:] = [d for d in dirs if d not in exclude]
        for name in files:
            if name == "OWNERS":
                yield os.path.join(root, name)

approvers = set()
reviewers = set()
components = set()

for owners_file in find_owner_files("."):
    for doc in read_owners_file(owners_file):
        if doc.get("approvers"):
            for approver in doc["approvers"]:
                approvers.add(approver)

        if doc.get("reviewers"):
            for reviewer in doc["reviewers"]:
                reviewers.add(reviewer)

        if doc.get("component"):
            components.add(doc["component"])

out = {
    "approvers": sorted(list(approvers)),
    "reviewers": sorted(list(reviewers)),
    "components": sorted(list(components)),
}

print(yaml.safe_dump(out))
