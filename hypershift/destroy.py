#!/usr/bin/env python3

from utils import Config, Defaults

import os
import json
import shutil
import subprocess
import sys


def get_hostedcluster(name):
    hostedclusters = get_hostedclusters()
    for hostedcluster in hostedclusters:
        if hostedcluster["metadata"]["name"] == name:
            return hostedcluster


def get_hostedclusters():
    out = subprocess.run([
            shutil.which("oc"),
            "get",
            "hostedclusters",
            "--all-namespaces",
            "-o=json"
        ], capture_output=True, env=os.environ)

    out.check_returncode()

    return json.loads(out.stdout)["items"]


def get_hypershift_delete_cmd(hostedcluster):
    args = [
        shutil.which("hypershift"),
        "destroy", "cluster", "aws",
        "--name", hostedcluster["metadata"]["name"],
        "--namespace", hostedcluster["metadata"]["namespace"],
        "--infra-id", hostedcluster["spec"]["infraID"],
        "--base-domain", Config.BASE_DOMAIN,
        "--aws-creds", Config.AWS_CONFIG_FILE
    ]

    print("Running: $", ' '.join(args))

    return subprocess.Popen(args, env=os.environ)


def get_namespace_delete_cmd(namespace):
    args = [
        shutil.which("oc"),
        "delete",
        "namespace/" + namespace
    ]

    print("Running: $", ' '.join(args))

    return subprocess.Popen(args, env=os.environ)


def wait_for_cmds(cmds):
    for cmd in cmds:
        cmd.wait()

    for cmd in cmds:
        if cmd.returncode != 0:
            sys.exit(cmd.returncode)


def execute(hostedclusters):
    if len(hostedclusters) == 0:
        print("Found no hosted clusters, nothing to do!")
        sys.exit(0)

    # Delete hosted clusters
    wait_for_cmds([get_hypershift_delete_cmd(hostedcluster)
                    for hostedcluster in hostedclusters])

    # Ensure the namespace is deleted
    wait_for_cmds([get_namespace_delete_cmd(hostedcluster["metadata"]["namespace"])
                    for hostedcluster in hostedclusters
                    if hostedcluster["metadata"]["namespace"] != Config.CLUSTERS_NAMESPACE])
