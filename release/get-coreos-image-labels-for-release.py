#!/usr/bin/env python3

import json
import os
import subprocess
import sys


def inspect_image(pullspec):
    cmd = subprocess.run(
        ["skopeo", "inspect", "--no-tags", f"docker://{pullspec}"], capture_output=True
    )
    cmd.check_returncode()
    return json.loads(cmd.stdout)


def get_oc_release_info(pullspec=None):
    args = ["oc", "adm", "release", "info", "--output", "json"]
    if pullspec:
        args.append(pullspec)

    cmd = subprocess.run(args, capture_output=True)
    cmd.check_returncode()
    return json.loads(cmd.stdout)


if len(sys.argv) == 1:
    print("Must provide an image pullspec")
    sys.exit(1)

# Fetch the release info from the given pullspec.
rel_info = get_oc_release_info(sys.argv[1])

# Filter only the image refs that contain the substring "coreos" to get the OS
# images for this release payload.
os_image_refs = [
    ref for ref in rel_info["references"]["spec"]["tags"] if "coreos" in ref["name"]
]

# Run skopeo inspect on each of the image refs. For now, we're only concerned
# about the labels on each image.
os_image_labels = {
    os_image_ref["name"]: inspect_image(os_image_ref["from"]["name"])["Labels"]
    for os_image_ref in os_image_refs
}

# Finally, build our report.
out = {
    "release_image": rel_info["image"],
    "release_version": rel_info["config"]["config"]["Labels"],
    "os_image_refs": os_image_refs,
    "os_image_labels": os_image_labels,
}

print(json.dumps(out, indent=4))
