#!/usr/bin/env python3

# Used to dump an OpenShift MachineConfig while decoding any encoded file
# contents and pretty-printing any JSON file contents found. It does not
# (currently) support expanding gzipped payloads.
#
# Typically used in conjunction with $ oc, e.g.:
# $ oc get mc/<machine-config-name> -o yaml | ./dump-machine-config.py -
#
# Can also be used to read from a file:
# $ ./dump-machine-config.py machine-config-file.yaml

from urllib.parse import unquote
import os
import json
import yaml
import sys


def str_presenter(dumper, data):
  if len(data.splitlines()) > 1:  # check for multiline string
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
  return dumper.represent_scalar('tag:yaml.org,2002:str', data)

yaml.add_representer(str, str_presenter)

# to use with safe_dump:
yaml.representer.SafeRepresenter.add_representer(str, str_presenter)

def load_machineconfig(filename):
  if filename != "-":
    with open(filename, "r") as mcfile:
        return list(yaml.safe_load_all(mcfile))

  return list(yaml.safe_load_all(sys.stdin.read()))

def get_contents(raw_content):
  unquoted = unquote(raw_content.replace("data:,", ""))
  # If empty, stop here.
  if unquoted == "":
    return unquoted

  try:
    # If we have JSON, lets pretty-print it!
    return json.dumps(json.loads(unquoted), indent=4, sort_keys=True)
  except json.decoder.JSONDecodeError:
    # We didn't have any JSON, so lets return
    return unquoted

def get_files_from_machineconfig(mc):
  files_out = {}

  # If the MachineConfig does not specify files, return early.
  if not mc["spec"]["config"].get("storage"):
    return files_out

  for mc_file in mc["spec"]["config"]["storage"]["files"]:
    # If we don't have a contents object, return early.
    contents = mc_file.get("contents")
    if not contents:
      continue

    # If the contents object does not have a source, return early.
    source = contents.get("source")
    if not source:
      continue

    # We have a source, let's extract it.
    files_out[mc_file["path"]] = get_contents(source)

  return files_out

def get_systemd_units_from_machineconfig(mc):
  systemd_root="/etc/systemd/system"

  systemd_out = {}

  # If the MachineConfig does not specify systemd units, return early.
  if not mc["spec"]["config"].get("systemd"):
    return systemd_out

  for systemd_unit in mc["spec"]["config"]["systemd"]["units"]:
    unit_name = systemd_unit["name"]

    # Append the systemd root path onto the systemd unit name
    filename = os.path.join(systemd_root, unit_name)

    # Allow dropins to be nested under the top-level systemd unit.
    info = {
      "dropins": {},
    }

    contents = systemd_unit.get("contents")
    if contents:
      info["contents"] = get_contents(contents)

    if not systemd_unit.get("dropins"):
      # The systemd unit specifies no dropins, so lets move onto the next one.
      systemd_out[filename] = info
      continue

    # Nest the dropins under the systemd unit we're looking at.
    for dropin in systemd_unit["dropins"]:
      # Append the ".d" onto the systemd unit name and append the dropin name to the path.
      dropin_filename = os.path.join(systemd_root, unit_name + ".d", dropin["name"])
      info["dropins"][dropin_filename] = get_contents(dropin.get("contents", ""))

    systemd_out[filename] = info

  return systemd_out

def get_output_from_machineconfig(mc):
  # Dispatch to both the file and systemd extraction functions.
  return {
    "files": get_files_from_machineconfig(mc),
    "systemd_units": get_systemd_units_from_machineconfig(mc),
  }

if __name__ == "__main__":
  out = {}
  machineconfigs = load_machineconfig(sys.argv[1])
  # If we only have a single machineconfig, we don't need to key by its name.
  if len(machineconfigs) == 1:
    out = get_output_from_machineconfig(machineconfigs[0])

  # If we have multiple machineconfigs, we should read each one and key by its name.
  if len(machineconfigs) > 1:
    for mc in machineconfigs:
      out[mc["metadata"]["name"]] = get_output_from_machineconfig(mc)

  print(yaml.safe_dump(out))
