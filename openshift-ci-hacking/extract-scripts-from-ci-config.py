#!/usr/bin/env python3

# This script extracts all the scripts from the tests section in a given
# OpenShift CI config file. Useful for extracting scripts for static analysis
# or relocation into one's project repo.

# Usage:
# $ ./extract-scripts-from-ci-config.py './ci-operator/config/path/to/config'

import os
import sys
import yaml

def load_config(path):
    with open(path, "r") as config:
        return list(yaml.safe_load_all(config))[0]

config_path = sys.argv[1]
config = load_config(config_path)
print("Loaded config from", config_path)
for test in config["tests"]:
    if test.get("commands"):
        outfilename = "{test_name}.sh".format(test_name=test["as"])
        print("Writing script for {test_name} to {outfilename}".format(test_name=test["as"], outfilename=outfilename))
        with open(outfilename, "w") as outfile:
            outfile.write(test["commands"])

    steps = test.get("steps")
    if not steps:
        continue

    if not steps.get("test"):
        continue

    for step in test["steps"]["test"]:
        outfilename = "{test_name}-{step_name}.sh".format(test_name=test["as"], step_name=step["as"])
        print("Writing script for {test_name}-{step_name} to {outfilename}".format(test_name=test["as"], step_name=step["as"], outfilename=outfilename))
        with open(outfilename, "w") as outfile:
            outfile.write(step["commands"])
