#!/usr/bin/env python3

import json
import subprocess

CREATED_LABEL="machineconfiguration.openshift.io/pool-created-by-zzlotnik-script"
MODIFIED_LABEL="machineconfiguration.openshift.io/pool-scaled-by-zzlotnik-script"
MACHINE_API_NAMESPACE="openshift-machine-api"
MCO_NAMESPACE="openshift-machine-config-operator"

def get_arm64_machineset_spec(infra_id, boot_image, template_machine, template_machineset):
  instance_type = "m6g.xlarge"

  region = template_machine["metadata"]["labels"]["machine.openshift.io/region"]
  zone = template_machine["metadata"]["labels"]["machine.openshift.io/zone"]
  role = template_machine["metadata"]["labels"]["machine.openshift.io/cluster-api-machine-role"]

  infra_role_zone = f"{infra_id}-{role}-{zone}"

  machineset = {
    "apiVersion": "machine.openshift.io/v1beta1",
    "kind": "MachineSet",
    "metadata": {
      "labels": {
        CREATED_LABEL: "",
        "machine.openshift.io/cluster-api-cluster": infra_id,
      },
      "name": f"{infra_id}-{role}-arm64",
      "namespace": "openshift-machine-api"
    },
    "spec": {
      "replicas": 2,
      "selector": {
        "matchLabels": {
          "machine.openshift.io/cluster-api-cluster": infra_id,
          "machine.openshift.io/cluster-api-machineset": infra_role_zone,
        },
      },
      "template": {
        "metadata": {
          "labels": {
            "machine.openshift.io/cluster-api-cluster": infra_id,
            "machine.openshift.io/cluster-api-machine-role": role,
            "machine.openshift.io/cluster-api-machine-type": role,
            "machine.openshift.io/cluster-api-machineset": infra_role_zone,
            CREATED_LABEL: "",
          }
        }
      }
    }
  }

  machineset["spec"]["template"]["spec"] = template_machineset["spec"]["template"]["spec"]
  machineset["spec"]["template"]["spec"]["providerSpec"]["value"]["ami"]["id"] = boot_image
  machineset["spec"]["template"]["spec"]["providerSpec"]["value"]["instanceType"] = instance_type
  return machineset

def run_oc_cmd_json(oc_cmd):
  cmd = subprocess.run(oc_cmd, capture_output=True)
  cmd.check_returncode()
  return json.loads(cmd.stdout)

def get_infra_id():
  return run_oc_cmd_json(["oc", "get", "infrastructure", "cluster", "-o", "json"])["status"]["infrastructureName"]

def get_machinesets():
  return run_oc_cmd_json(["oc", "get", "machinesets", "-n" "openshift-machine-api", "-l", f"!{CREATED_LABEL}", "-o", "json"])["items"]

def get_machines_from_machineset(machineset_name):
  label_query = f"machine.openshift.io/cluster-api-machineset={machineset_name}"
  return run_oc_cmd_json(["oc", "get", "machines", "-n", MACHINE_API_NAMESPACE, "-l", label_query, "-o", "json"])

def get_bootimages(arch="aarch64", region="us-east-1"):
  images_config_map = run_oc_cmd_json(["oc", "get", "configmap/coreos-bootimages", "-n", MCO_NAMESPACE, "-o", "json"])
  images = json.loads(images_config_map["data"]["stream"])
  return images["architectures"][arch]["images"]["aws"]["regions"][region]["image"]

def apply_object(obj, namespace):
  cmd = ["oc", "apply", "--namespace", namespace, "--filename", "-"]
  subprocess.run(cmd, text=True, input=json.dumps(obj)).check_returncode()

def scale_down_template_machineset(machineset):
  machineset_name = f"machineset/{machineset['metadata']['name']}"
  cmd = ["oc", "scale", "--replicas", "2", "--namespace", MACHINE_API_NAMESPACE, machineset_name]
  subprocess.run(cmd).check_returncode()

  original_replicas = machineset["spec"]["replicas"]
  pool_scaled_label = f"{MODIFIED_LABEL}={original_replicas}"

  cmd = ["oc", "label", "--namespace", MACHINE_API_NAMESPACE, machineset_name, pool_scaled_label]
  subprocess.run(cmd).check_returncode()

def main():
  infra_id = get_infra_id()
  print(f"Found infra ID: {infra_id}")
  template_machineset = get_machinesets()[0]
  machineset_name = template_machineset["metadata"]["name"]
  print(f"Found MachineSet: {machineset_name}")
  template_machine = get_machines_from_machineset(machineset_name)["items"][0]
  print(f"Extracting data from Machine {template_machine['metadata']['name']}")
  region = template_machine["metadata"]["labels"]["machine.openshift.io/region"]
  boot_image = get_bootimages("aarch64", region)
  arm64_spec = get_arm64_machineset_spec(infra_id, boot_image, template_machine, template_machineset)
  apply_object(arm64_spec, MACHINE_API_NAMESPACE)
  scale_down_template_machineset(template_machineset)

if __name__ == "__main__":
  main()
