#!/usr/bin/env python3

from urllib.parse import unquote
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
  if unquoted == "":
    return unquoted

  try:
    return json.dumps(json.loads(unquoted), indent=4, sort_keys=True)
  except json.decoder.JSONDecodeError:
    return unquoted

out = {}

for doc in load_machineconfig(sys.argv[1]):
    for mc_file in doc["spec"]["config"]["storage"]["files"]:
        out[mc_file["path"]] = get_contents(mc_file["contents"]["source"])

print(yaml.safe_dump(out))
