#!/usr/bin/env python3

import json
import subprocess

CREATED_LABEL="machineconfiguration.openshift.io/pool-created-by-zzlotnik-script"
MODIFIED_LABEL="machineconfiguration.openshift.io/pool-scaled-by-zzlotnik-script"
MACHINE_API_NAMESPACE="openshift-machine-api"
MCO_NAMESPACE="openshift-machine-config-operator"

def run_oc_cmd_json(oc_cmd):
    cmd = subprocess.run(oc_cmd, capture_output=True)
    cmd.check_returncode()
    return json.loads(cmd.stdout)

def get_machinesets():
  return run_oc_cmd_json(["oc", "get", "machinesets", "-n" "openshift-machine-api", "-o", "json"])["items"]

def delete_machineset(machineset):
  subprocess.run(["oc", "delete", "-n", MACHINE_API_NAMESPACE, f"machineset/{machineset['metadata']['name']}"]).check_returncode

def restore_machineset(machineset):
  original_replicas = machineset["metadata"]["labels"][MODIFIED_LABEL]
  machineset_name = f"machineset/{machineset['metadata']['name']}"

  cmd = ["oc", "scale", "--replicas", original_replicas, "--namespace", MACHINE_API_NAMESPACE, machineset_name]
  subprocess.run(cmd).check_returncode()

  modified_label = f"{MODIFIED_LABEL}-"

  cmd = ["oc", "label", "--namespace", MACHINE_API_NAMESPACE, machineset_name, modified_label]
  subprocess.run(cmd).check_returncode()

def main():
  for machineset in get_machinesets():
    if CREATED_LABEL in machineset["metadata"]["labels"]:
      print(f"Will delete {machineset['metadata']['name']}")
      delete_machineset(machineset)
      continue

    if MODIFIED_LABEL in machineset["metadata"]["labels"]:
      original_replicas = machineset["metadata"]["labels"][MODIFIED_LABEL]
      print(f"Will restore replicas to {original_replicas} for {machineset['metadata']['name']}")
      restore_machineset(machineset)
      continue

    print(f"Machineset {machineset['metadata']['name']} missing labels {[CREATED_LABEL, MODIFIED_LABEL]}, skipping!")


if __name__ == "__main__":
  main()
