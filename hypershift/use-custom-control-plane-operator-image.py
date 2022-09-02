#!/usr/bin/env python3

import utils

import argparse
import os
import json
import shutil
import subprocess
import sys


def get_args(name):
    parser = argparse.ArgumentParser(parents=[utils.get_default_args(__file__)])

    parser.add_argument(
        "--image", default=utils.Defaults.CONTROL_PLANE_IMAGE, dest="image", required=True)

    return parser.parse_args()


if __name__ == "__main__":
    args = get_args(__file__)
    utils.use_custom_control_plane_operator(image=args.image, cluster_name=args.cluster_name)
