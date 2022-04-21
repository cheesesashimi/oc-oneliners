#!/usr/bin/env python3

# This is a companion script to the inject-script-into-ci-config.py script
# found in this repo. It extracts the script from a failed CI test pod spec.
# Usage:
# 1. Retrieve the spec for the failed pod:
#    $ oc get pod/<pod name> -o yaml > failed-pod.yaml
# 2. Extract the script from the pod by running this script:
#    $ ./extract-script-from-ci-test-podspec.py ./failed-pod.yaml ./failed-pod-script.sh

import json
import sys
import yaml

def load_pod_yaml(path):
    print("Reading YAML from:", path)
    with open(path, "r") as pod_yaml:
        return list(yaml.safe_load_all(pod_yaml))[0]

pod_yaml_path = sys.argv[1]
output_path = sys.argv[2]

pod = load_pod_yaml(pod_yaml_path)
entrypoint_options_json = json.loads(pod["spec"]["containers"][0]["env"][14]["value"])
script = entrypoint_options_json["args"][2]

print("Writing script to:", output_path)
with open(output_path, "w") as script_out:
    script_out.write(script)
