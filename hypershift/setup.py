#!/usr/bin/env python3

from create import create_hosted_cluster
from utils import Config, Defaults, use_custom_control_plane_operator
import argparse
import os
import shutil
import subprocess

default_hypershift_image = "quay.io/hypershift/hypershift-operator:latest"

def create_s3_bucket():
    out = subprocess.run([
        shutil.which("aws"),
        "s3api",
        "create-bucket",
        "--acl", "public-read",
        "--bucket", Config.BUCKET_NAME,
        "--region", Config.REGION,
    ], env=os.environ)

    out.check_returncode()

def render_hypershift_manifests(install_args):
    out = subprocess.run([
        shutil.which("hypershift"),
        "install",
        "render",
        ] + install_args, capture_output=True)

    out.check_returncode()

    with open(Config.MANIFESTS_FILE, "wb") as manifests_file:
        print("Storing Hypershift manifests in:", Config.MANIFESTS_FILE)
        manifests_file.write(out.stdout)

def install_hypershift(install_args):
    out = subprocess.run([
        shutil.which("hypershift"),
        "install"
    ] + install_args)

    out.check_returncode()

def setup(hypershift_image, cluster_name, release):
    use_custom_hypershift_image = hypershift_image != default_hypershift_image

    create_s3_bucket()

    install_args = [
        "--oidc-storage-provider-s3-bucket-name", Config.BUCKET_NAME,
        "--oidc-storage-provider-s3-credentials", Config.AWS_CONFIG_FILE,
        "--oidc-storage-provider-s3-region", Config.REGION,
    ]

    if use_custom_hypershift_image:
        install_args.extend(["--hypershift-image", hypershift_image])

    render_hypershift_manifests(install_args)
    install_hypershift(install_args)

    if cluster_name:
        print("Will create new cluster called", cluster_name)
        create_hosted_cluster(cluster_name, release)

        if use_custom_hypershift_image:
            print("Hosted cluster", cluster_name, "will use custom image", hypershift_image)
            use_custom_control_plane_operator(hypershift_image, cluster_name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hypershift-image", required=False, default=default_hypershift_image, dest="hypershift_image")
    parser.add_argument(
        "--cluster-name", required=False, default=None, dest="cluster_name")
    parser.add_argument(
        "--release", required=False, default=None, dest="release")

    parsed = parser.parse_args()
    setup(parsed.hypershift_image, parsed.cluster_name, parsed.release)


if __name__ == "__main__":
    main()
