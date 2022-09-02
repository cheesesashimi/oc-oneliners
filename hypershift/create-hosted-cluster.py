#!/usr/bin/env python3

from utils import Config, get_default_args
from create import create_hosted_cluster

import argparse


def main():
    parser = argparse.ArgumentParser(parents=[get_default_args(__file__)],
            description="Creates a hosted cluster in a given OpenShift Hypershift controlplane")
    parser.add_argument(
            "--release", default=None, dest="release", required=False)
    parsed = parser.parse_args()
    create_hosted_cluster(parsed.cluster_name, parsed.release)


if __name__ == "__main__":
    main()
