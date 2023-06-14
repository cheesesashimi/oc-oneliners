#!/usr/bin/env python3

from pathlib import Path

import json
import os
import requests
import shutil
import subprocess
import sys
import yaml

USERNAME = "zzlotnik"
PULL_SECRET_PATH = os.path.join(Path.home(), ".docker/config.json")
SSH_KEY_PATH = os.path.join(Path.home(), ".ssh/id_ed25519.pub")

def get_image_digest(pullspec):
  # Prefer skopeo for this because it's faster...
  if shutil.which("skopeo"):
    cmd_args = ["skopeo", "inspect", f"--authfile={PULL_SECRET_PATH}", f"docker://{pullspec}"]
    key = "Digest"
  else:
    cmd_args = ["oc", "image", "info", "-o=json", f"--registry-config={PULL_SECRET_PATH}", pullspec]
    key = "digest"

  cmd = subprocess.run(cmd_args, capture_output=True)
  cmd.check_returncode()
  return json.loads(cmd.stdout)[key]

def get_release_image_from_file(flavor, arch, release_stream):
  release_file_names = [".openshift_release", ".okd_release", ".okd_scos_release", ".ocp_release"]
  for release_file_name in release_file_names + [name.replace("_", "-") for name in release_file_names]:
    release_image_file = os.path.join(get_run_dir(flavor, arch), release_file_name)
    if os.path.exists(release_image_file):
      with open(release_image_file, "r"):
        release_image_pullspec = release_image_file.read().strip()
        print(f"Found {release_image_file}, will use {release_image_pullspec}")
        return release_image_pullspec

def get_release_image(flavor, arch, release_stream):
  release_pullspec = get_release_image_from_file(flavor, arch, release_stream)
  if release_pullspec:
    return release_pullspec

  flavors = {
    "okd": f"https://{arch}.origin.releases.ci.openshift.org/api/v1/releasestream/{release_stream}/latest",
    # OKD-SCOS uses the same release controller as OKD. It just uses a different release stream.
    "okd-scos": f"https://{arch}.origin.releases.ci.openshift.org/api/v1/releasestream/{release_stream}/latest",
    "ocp": f"https://{arch}.ocp.releases.ci.openshift.org/api/v1/releasestream/{release_stream}/latest",
  }

  result = requests.get(flavors[flavor])
  if result.status_code != 200:
    print("could not get release image:")
    print(result.request)
    sys.exit(1)

  release_image_pullspec = result.json()["pullSpec"]
  print(f"Queried {flavors[flavor]} and found {release_image_pullspec}")
  return release_image_pullspec

def get_ssh_keys():
  with open(SSH_KEY_PATH, "r") as ssh_key_file:
    return ssh_key_file.read()

def get_pull_config():
  with open(PULL_SECRET_PATH, "r") as pull_secret_file:
    pull_config = pull_secret_file.read()
    pull_config = {"auths": json.loads(pull_config)["auths"]}
    return json.dumps(pull_config)

def get_run_dir(flavor, arch):
  cluster_name = get_cluster_name(flavor, arch)
  return os.path.join(Path.home(), f".{cluster_name}")

def get_cluster_name(flavor, arch):
  return f"{USERNAME}-{flavor}-{arch}"

def get_install_config(flavor, arch):
  return {
    "apiVersion": "v1",
    "baseDomain": "devcluster.openshift.com",
    "compute": [
      {
        "architecture": arch,
        "hyperthreading": "Enabled",
        "name": "worker",
        "platform": {},
        "replicas": 3
      }
    ],
    "controlPlane": {
      "architecture": arch,
      "hyperthreading": "Enabled",
      "name": "master",
      "platform": {},
      "replicas": 3
    },
    "metadata": {
      "creationTimestamp": None,
      "name": get_cluster_name(flavor, arch)
    },
    "networking": {
      "clusterNetwork": [
        {
          "cidr": "10.128.0.0/14",
          "hostPrefix": 23
        }
      ],
      "machineNetwork": [
        {
          "cidr": "10.0.0.0/16"
        }
      ],
      "networkType": "OpenShiftSDN",
      "serviceNetwork": [
        "172.30.0.0/16"
      ]
    },
    "platform": {
      "aws": {
        "region": "us-east-1"
      }
    },
    "publish": "External",
    "pullSecret": get_pull_config(),
    "sshKey": get_ssh_keys(),
  }

def get_installer(run_dir, release_image):
  cmd_args = ["oc", "adm", "release", "extract", f"--registry-config={PULL_SECRET_PATH}", "--command=openshift-install", f"--to={run_dir}", release_image]
  cmd_args_joined = ' '.join(cmd_args)
  print(f"Extracting installer using $ {cmd_args_joined}")
  cmd = subprocess.run(cmd_args)
  cmd.check_returncode()

def installer_matches_digest(run_dir, release_image_digest):
  cmd = subprocess.run([os.path.join(run_dir, "openshift-install"), "version"], capture_output=True)
  cmd.check_returncode()
  return release_image_digest in cmd.stdout.encode("utf-8")

def does_cluster_exist(run_dir):
  assets = ["metadata.json", "auth/kubeconfig", ".openshift_install.log", ".openshift_install_state.json"]
  for asset in assets:
    asset_path = os.path.join(run_dir, asset)
    if os.path.exists(asset_path):
      print(f"Found {asset_path}")
      return True

def run_installer(run_dir):
  installer_path = os.path.join(run_dir, "openshift-install")
  print(f"Starting installation process:")
  cmd = subprocess.run([installer_path, "version"])
  cmd.check_returncode()
  cmd = subprocess.run([installer_path, "--log-level", "debug", "create", "cluster", "--dir", run_dir])
  cmd.check_returncode()

def provision_cluster(flavor, arch, release_stream):
  run_dir = get_run_dir(flavor, arch)
  if does_cluster_exist(run_dir):
    sys.exit(1)

  os.makedirs(run_dir, exist_ok=True)
  release_image = get_release_image(flavor, arch, release_stream)
  release_image_digest = get_image_digest(release_image)
  print(f"Release image {release_image} has digest {release_image_digest}")
  install_config = get_install_config(flavor, arch)
  with open(os.path.join(run_dir, "install-config.yaml"), "w") as install_config_file:
    install_config_file.write(yaml.safe_dump(install_config))

  installer_path = os.path.join(run_dir, "openshift-install")
  if os.path.exists(installer_path):
    print(f"Found preexisting installer for {release_image_digest} at {installer_path}")
  else:
    print(f"Retrieving installer for {release_image_digest}")
    get_installer(run_dir, release_image)

  run_installer(run_dir)

provision_cluster("ocp", "arm64", "4-stable-arm64")
#provision_cluster("okd", "amd64", "4-stable")
#provision_cluster("okd-scos", "amd64", "4-scos-stable")
