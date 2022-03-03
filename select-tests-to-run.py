#!/usr/bin/env python3

# This script is useful for selecting a subset of tests in a given ci-operator config to run.

import os
import yaml

ci_operator_config_file = "ci-operator/config/openshift/machine-config-operator/openshift-machine-config-operator-layering.yaml"

tests_to_run = frozenset((
    "e2e-aws",
    "e2e-aws-upgrade",
    "e2e-gcp-op",
    "e2e-gcp-op-single-node",
    "e2e-gcp-single-node",
    "unit",
    "verify"
))

with open(ci_operator_config_file, "r") as test_config_file:
    test_config = list(yaml.safe_load_all(test_config_file))[0]

test_configs_to_run = []
for test in test_config["tests"]:
    if test["as"] not in tests_to_run:
        continue
    test_configs_to_run.append(test)

test_config["tests"] = test_configs_to_run

with open(ci_operator_config_file, "w") as test_config_file:
    yaml.safe_dump(test_config, test_config_file)
