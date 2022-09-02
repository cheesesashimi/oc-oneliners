#!/usr/bin/env python3

from utils import Config, Defaults

import os
import subprocess
import sys
import urllib.parse
import yaml

DATA_PREFIX = "data:,"
CONFIGMAP_NAME = "configmap/" + Defaults.MACHINECONFIG

# Needed to not have nested YAML sprinkled with newlines
def str_presenter(dumper, data):
  if len(data.splitlines()) > 1:  # check for multiline string
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
  return dumper.represent_scalar('tag:yaml.org,2002:str', data)

yaml.add_representer(str, str_presenter)

# to use with safe_dump:
yaml.representer.SafeRepresenter.add_representer(str, str_presenter)


def get_initial_machineconfig():
    # Get ConfigMap
    oc_proc = subprocess.run(["oc", "get", CONFIGMAP_NAME, "-n", Config.CLUSTERS_NAMESPACE, "-o", "yaml"], capture_output=True)
    if oc_proc.returncode != 0:
        print(oc_proc.stdout)
        print(oc_proc.stderr)
        sys.exit(oc_proc.returncode)

    # Note: yaml.safe_load_all returns a generator to handle multiple YAML
    # documents. Rather than iterate for a single document, we pass the
    # generator into list() and get the first (and only) YAML document.
    configmap = list(yaml.safe_load_all(oc_proc.stdout))[0]

    # Unpack the MachineConfig from ConfigMap.
    return list(yaml.safe_load_all(configmap["data"]["config"]))[0]


def decode_and_increment_file_content(content):
    # Unquote the contents
    content = urllib.parse.unquote(content)

    # Strip any newlines
    content = content.strip()

    # Remove the data prefix
    content = content.replace(DATA_PREFIX, "")

    # Cast to integer so we can increment it
    content = int(content)

    # Increment it
    content += 1

    # Cast to string and add a new-line (the new-line is not strictly necessary)
    content = str(content) + "\n"

    # Cast to string and urlquote it
    content = urllib.parse.quote(content)

    # Add the data prefix; and we're done!
    return DATA_PREFIX + content


def prepare_patch(machineconfig):
    return {
        "data": {
            "config": yaml.safe_dump(machineconfig)
        }
    }


def apply_patch(patch):
    dumped_patch = yaml.safe_dump(patch)
    patch_arg = "--patch=" + dumped_patch
    return subprocess.run(["oc", "patch", CONFIGMAP_NAME, "-n", Config.CLUSTERS_NAMESPACE, patch_arg, "--type=merge"])


machineconfig = get_initial_machineconfig()

file_content = machineconfig["spec"]["config"]["storage"]["files"][0]["contents"]["source"]
incremented_file_content = decode_and_increment_file_content(file_content)
machineconfig["spec"]["config"]["storage"]["files"][0]["contents"]["source"] = incremented_file_content

patch = prepare_patch(machineconfig)
result = apply_patch(patch)
sys.exit(result.returncode)
