#!/usr/bin/env python3

# This script is for use with the OpenShift CI system to enable faster feedback
# loops when updating CI configuration. For context:
# - When CI configs are updated, the CI system will attempt to run
# jobs with the new configs (referred to as a rehearsal).
# - The author of the config changes is granted access to the ephemeral
# namespace where the CI job is run. Regardless of a pass or failure, the
# ephemeral namespace remains for approximately 1 hour after the job completes
# to allow the author to inspect the environment, pull any built images, etc.
# - Instead of making a change to the config, pushing those changes, and
# waiting for feedback, it is faster and easier to create a new pod with your
# changes. However, because of how the CI system ingests the scripts from the
# config, injecting those changes can be tedious, hence the reason for this
# script.
#
# To use this script:
# 1. Log into the CI cluster by obtaining the cluster CI URL from the Prowjob
#    page.
# 2. Retrieve the spec for the failed pod:
#    $ oc get pod/<podname> -o yaml > failed-pod.yaml
# 3. Extract the script from the failed pod by using the
#    extract-script-from-ci-test-podspec.py script in this repo, e.g.:
#    $ ./extract-script-from-ci-test-podspec.py ./failed-pod.yaml ./failed-pod-script.sh
# 4. Edit failed-pod-script.sh to make your desired changes.
# 5. Run this script:
#    $ ./inject-script-into-ci-tset-podspec.py ./script-to-run-in-ci.sh ./failed-pod.yaml
# 6. Delete the failed pod and apply the updated YAML to verify your changes:
#    $ oc delete -f ./failed-pod.yaml && oc apply -f ./failed-pod.yaml.
# 7. Watch the pod logs in the CI console.
# 8. Repeat steps 4-8 until your config behaves as intended.
# 9. Update the CI config with your new script.

import json
import sys
import yaml

def clean_pod_yaml(pod):
    print("Stripping unnecessary pod data")
    keys_to_delete = {
        "metadata": [
            "annotations",
            "creationTimestamp",
            "labels",
            "resourceVersion",
            "uid",
        ],
        "spec": [
            "nodeName",
        ],
        "status": [],
    }

    for key, values in keys_to_delete.items():
        if len(values) == 0:
            if pod.get(key):
                print("Deleting", key)
                del pod[key]
                continue

        for value in values:
            if pod.get(key, {}).get(value):
                print("Deleting", value, "under", key)
                del pod[key][value]

    return pod

def inject_script_into_pod(script_path, pod):
    script = load_script(script_path)
    print("Injecting script into pod spec")

    entrypoint_options_json = json.loads(pod["spec"]["containers"][0]["env"][14]["value"])
    entrypoint_options_json["args"][2] = script

    sidecar_options_json = json.loads(pod["spec"]["containers"][1]["env"][1]["value"])
    sidecar_options_json["entries"][0]["args"][2] = script

    pod["spec"]["containers"][0]["env"][14]["value"] = json.dumps(entrypoint_options_json)
    pod["spec"]["containers"][1]["env"][1]["value"] = json.dumps(sidecar_options_json)

    return pod

def load_pod_yaml(path):
    print("Reading YAML from:", path)
    with open(path, "r") as pod_yaml:
        return clean_pod_yaml(list(yaml.safe_load_all(pod_yaml))[0])

def write_pod_yaml(pod, pod_yaml_path):
    print("Writing YAML to:", pod_yaml_path)
    with open(pod_yaml_path, "w") as pod_yaml_out:
        yaml.safe_dump(pod, pod_yaml_out)

def load_script(path):
    print("Reading script from:", path)
    with open(path, "r") as script:
        return ''.join(script.readlines()).strip()

script_path = sys.argv[1]
pod_yaml_path = sys.argv[2]

pod = load_pod_yaml(pod_yaml_path)
pod = inject_script_into_pod(script_path, pod)

write_pod_yaml(pod, pod_yaml_path)
