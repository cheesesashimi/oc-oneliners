#!/usr/bin/env python3

import argparse
import getpass
import os
import json
import shutil
import subprocess
import sys
from pathlib import Path

homedir=str(Path.home())
user = getpass.getuser()

required_commands = ["aws", "hypershift", "oc"]
for cmd in required_commands:
    if not shutil.which(cmd):
        print("Required command", cmd, "not found!")
        sys.exit(1)


def inplace_upgrade_name(cluster_name):
    return "inplace-upgrade-" + cluster_name


class Config(object):
    AWS_CONFIG_FILE = os.path.join(homedir, ".aws/credentials")
    BASE_DOMAIN = "devcluster.openshift.com"
    BUCKET_NAME = user + "-hypershift-bucket"
    CLUSTERS_NAMESPACE = "clusters"
    HOSTED_CLUSTER_TYPE = "hostedcluster.hypershift.openshift.io"
    MANIFESTS_FILE = os.path.join(os.getcwd(), "hypershift-manifests.yaml")
    REGION = "us-east-1"
    REGISTRY_AUTH_FILE = os.path.join(homedir, ".docker/config.json")


class Defaults(object):
    OPERATOR_IMAGE = "quay.io/hypershift/hypershift-operator:latest"
    CONTROL_PLANE_IMAGE = "quay.io/" + user + "control-plane-operator:latest"
    CLUSTER_NAME = user + "-hosted-cluster"
    MACHINECONFIG = "test-machineconfig"
    MACHINECONFIG_PATH = os.path.join(os.path.dirname(__file__), "test-machineconfig-configmap.yaml")
    INPLACE_UPGRADE_NODEPOOL = inplace_upgrade_name(CLUSTER_NAME)


def get_default_args(filename):
    parser = argparse.ArgumentParser(
        "usage: %s [OPTION] ..." % os.path.basename(filename),
        add_help=False
    )

    parser.add_argument(
        "--cluster-name", default=Defaults.CLUSTER_NAME, dest="cluster_name")

    return parser


def run_cmd_and_check(args):
    print("Running: $", ' '.join(args))
    out = subprocess.run(args, env=os.environ)
    out.check_returncode()


def use_custom_control_plane_operator(image, cluster_name):
    patch = {
        "metadata": {
            "annotations": {
                "hypershift.openshift.io/control-plane-operator-image": image,
            }
        }
    }

    cmd = subprocess.run([
        shutil.which("oc"),
        "patch",
        "hostedcluster/" + cluster_name,
        "--namespace", Config.CLUSTERS_NAMESPACE,
        "--patch=" + json.dumps(patch),
        "--type=merge"
    ], env=os.environ)

    cmd.check_returncode()

    print("Hosted cluster", cluster_name, "configured to use", image)


def byte_to_str(b):
    return b.decode("utf-8").strip("'").strip("\"")
