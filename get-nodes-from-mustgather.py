#!/usr/bin/env python3

from collections import defaultdict

import os
import yaml

def load_yaml(filename):
    with open(filename, "r") as yamlfile:
        return list(yaml.safe_load_all(yamlfile))[0]

def get_node_roles(node):
    node_role_key = "node-role.kubernetes.io/"
    return [label.replace(node_role_key, "")
            for label in node["metadata"]["labels"].keys()
            if node_role_key in label]

def get_node_state(node):
    if node["metadata"]["annotations"]["machineconfiguration.openshift.io/state"] == "Done":
        return "Done"

    return "%(machineconfiguration.openshift.io/state)s - %(machineconfiguration.openshift.io/reason)s" % node["metadata"]["annotations"]

def get_node_details(node):
    return {
        "Name": node["metadata"]["name"],
        "Current Config": node["metadata"]["annotations"]["machineconfiguration.openshift.io/currentConfig"],
        "Desired Config": node["metadata"]["annotations"]["machineconfiguration.openshift.io/desiredConfig"],
        "Roles": get_node_roles(node),
        "State": get_node_state(node),
    }

def print_node_details(node):
    row_order = [
        "Name",
        "Roles",
        "Current Config",
        "Desired Config",
        "State",
    ]

    for item in row_order:
        print("%s:\t%s" % (item, node[item]))

def get_node_details_from_files(root_path):
    for root, dirs, files in os.walk(root_path):
        for filename in files:
            full_filename = os.path.join(root, filename)
            try:
                yield full_filename, get_node_details(load_yaml(full_filename))
            except yaml.scanner.ScannerError:
                yield full_filename, None

by_role = defaultdict(list)
err_files = []

for filename, node_detail in get_node_details_from_files("./cluster-scoped-resources/core/nodes"):
    if not node_detail:
        err_files.append(filename)
        continue

    for role in node_detail["Roles"]:
        by_role[role].append(node_detail)

for role, nodes in by_role.items():
    by_role[role].sort(key=lambda x: x["Name"])

sorted_roles = sorted(list(by_role.keys()))

for role in sorted_roles:
    header = "Found %s nodes for role %s:" % (len(by_role[role]), role)
    print(header)
    print("=" * len(header))
    for node in by_role[role]:
        print_node_details(node)
        print("\n")

print("Node count by role:")
print("===================")
for role in sorted_roles:
    print("%s:\t%s" % (role, len(by_role[role])))

for role in sorted_roles:
    for node in by_role[role]:
        if node["Current Config"] != node["Desired Config"]:
            print("Node", node["name"], "has mismatched configs, current:", node["Current Config"], "desired:", node["Desired Config"])

if len(err_files) != 0:
    print("The following files were skipped due to errors:")
    for filename in err_files:
        print(filename)
