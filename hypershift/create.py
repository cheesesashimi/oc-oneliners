#!/usr/bin/env python3

from utils import Config

import os
import shutil
import subprocess


def create_hosted_cluster(cluster_name, release=None):
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

    if release:
        print("Will use OpenShift release", release, "for the hosted cluster")
        hypershift_args.extend(["--release-image", release])

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

    infra_id = str(out.stdout)

    infra_id_filename = os.path.join(os.getcwd(), cluster_name + "-infra-id")
    with open(infra_id_filename, "w") as infra_id_file:
        infra_id_file.write(infra_id)

    print("Your hosted cluster", cluster_name, "has infra ID:", infra_id)
    print("The infra ID has been saved to:", infra_id_filename)
