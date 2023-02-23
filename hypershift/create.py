#!/usr/bin/env python3

from utils import Config, Defaults, byte_to_str

import os
import shutil
import subprocess


def get_management_cluster_release_version():
    out = subprocess.run([
        shutil.which("oc"),
        "get",
        "clusterversion",
        "-o", "jsonpath='{.items[0].status.desired.image}'"
    ], capture_output=True, env=os.environ)
    out.check_returncode()
    return byte_to_str(out.stdout)


def get_hypershift_operator_image_pullspec():
    # Get the container pullspec for the Hypershift Operator so we can
    # explicitly specify that we want our hosted cluster to use it.
    out = subprocess.run([
        shutil.which("oc"),
        "get",
        "deployment/operator",
        "--namespace", "hypershift",
        "-o", "jsonpath='{.spec.template.spec.containers[0].image}'"
    ], capture_output=True, env=os.environ)
    out.check_returncode()
    return byte_to_str(out.stdout)


def get_hypershift_args(cluster_name, release):
    hypershift_operator_image = get_hypershift_operator_image_pullspec()

    hypershift_args = [
        shutil.which("hypershift"),
        "create", "cluster", "aws",
            "--name", cluster_name,
            "--node-pool-replicas", "1",
            "--base-domain", Config.BASE_DOMAIN,
            "--pull-secret", Config.REGISTRY_AUTH_FILE,
            "--aws-creds", Config.AWS_CONFIG_FILE,
            "--region", Config.REGION,
            "--generate-ssh",
    ]

    if hypershift_operator_image != Defaults.OPERATOR_IMAGE:
        hypershift_args.extend(["--control-plane-operator-image", hypershift_operator_image])

    if release:
        print("Will use provided OpenShift release", release, "for the hosted cluster")
    else:
        release = get_management_cluster_release_version()
        print("Defaulting to using the management cluster OpenShift release", release, "for the hosted cluster")

    hypershift_args.extend(["--release-image", release])

    return hypershift_args

def create_hosted_cluster(cluster_name, release=None):
    hypershift_args = get_hypershift_args(cluster_name, release)
    print("Running: $", ' '.join(hypershift_args))
    out = subprocess.run(hypershift_args)
    out.check_returncode()

    out = subprocess.run([
        shutil.which("oc"),
        "get",
        "%s/%s" % (Config.HOSTED_CLUSTER_TYPE, cluster_name),
        "--namespace", Config.CLUSTERS_NAMESPACE,
        "-o", "jsonpath='{.spec.infraID}'",
    ], capture_output=True, env=os.environ)

    out.check_returncode()

    infra_id = byte_to_str(out.stdout)

    infra_id_filename = os.path.join(os.getcwd(), cluster_name + "-infra-id")
    with open(infra_id_filename, "w") as infra_id_file:
        infra_id_file.write(infra_id)

    print("Your hosted cluster", cluster_name, "has infra ID:", infra_id)
    print("The infra ID has been saved to:", infra_id_filename)
