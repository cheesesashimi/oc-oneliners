#!/usr/bin/env python3

from utils import Config

import os
import subprocess

commands_to_run = [
    [os.path.join(os.path.dirname(__file__), "destroy-hosted-clusters.py")],
    ["oc", "delete", "-f", Config.MANIFESTS_FILE],
    ["aws", "s3api", "delete-bucket", "--bucket", Config.BUCKET_NAME]
]

print(os.path.join(os.path.dirname(__file__), "destroy-hosted-clusters.py"))

for cmd in commands_to_run:
    subprocess.run(cmd).check_returncode()
