#!/usr/bin/env python3

from utils import Config, Defaults, get_default_args, inplace_upgrade_name
import argparse
import os
import shutil
import subprocess
import yaml

def generate_nodepool_manifest(cluster_name, nodepool_name):
    # This only renders the YAML. It does not create the object. This is so we
    # can customize it before applying it.
    cmd = subprocess.run([
        shutil.which("hypershift"),
        "create", "nodepool", "aws",
        "--cluster-name", cluster_name,
        "--name", nodepool_name,
        "--node-count", "1",
        "--render"
    ], capture_output=True, env=os.environ)

    cmd.check_returncode()

    return list(yaml.safe_load_all(cmd.stdout))[0]


def create_nodepool(nodepool_manifest):
    cmd = subprocess.Popen([
        shutil.which("oc"),
        "apply",
        "-f"
        "-"
    ], stdin=subprocess.PIPE, env=os.environ)
    stdout, stderr = cmd.communicate(input=bytes(yaml.dump(nodepool_manifest), "utf-8"))
    cmd.wait()
    if cmd.returncode != 0:
        print(stdout)
        print(stderr)
        sys.exit(cmd.returncode)


def main(cluster_name, nodepool_name, add_machineconfig, machineconfig=Defaults.MACHINECONFIG):
    print("Creating nodepool", nodepool_name, "if it does not exist")

    nodepool_manifest = generate_nodepool_manifest(cluster_name, nodepool_name)

    # Change upgrade type to InPlace
    nodepool_manifest["spec"]["management"]["upgradeType"] = "InPlace"

    if add_machineconfig:
        print("Applying", os.path.basename(Defaults.MACHINECONFIG_PATH))
        out = subprocess.run([
            shutil.which("oc"),
            "apply",
            "-f", Defaults.MACHINECONFIG_PATH,
        ])

        out.check_returncode()

        # Configure the nodepool object to use the test-machineconfig
        print("Configuring nodepool to use machineconfig", Defaults.MACHINECONFIG)
        nodepool_manifest["spec"]["config"] = [{"name": Defaults.MACHINECONFIG}]

    create_nodepool(nodepool_manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(parents=[get_default_args(__file__)])

    parser.add_argument("--add-machineconfig", action="store_true", default=False, required=False, dest="add_machineconfig")
    parser.add_argument("--nodepool-name", default=Defaults.INPLACE_UPGRADE_NODEPOOL, required=False, dest="nodepool_name")

    args = parser.parse_args()

    main(args.cluster_name, args.nodepool_name, args.add_machineconfig)
