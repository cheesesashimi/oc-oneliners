#!/usr/bin/env python3

from collections import defaultdict
from dataclasses import dataclass

import csv
import json
import os
import subprocess


# Represents a single OCP release version containing all of the RHEL and Golang
# versions.
class OCP(object):
    def __init__(self, split_tags):
        self.openshift = split_tags[0].openshift

        rhel_versions = set()
        golang_versions = set()
        golang_versions_by_rhel = defaultdict(set)

        for split_tag in split_tags:
            rhel_versions.add(split_tag.rhel)
            golang_versions.add(split_tag.golang)
            golang_versions_by_rhel[split_tag.rhel].add(split_tag.golang)

        self.rhel_versions = sorted(list(rhel_versions))
        self.golang_versions = sorted(list(golang_versions))
        self.golang_by_rhel_version = {
            rhel_version: sorted(list(golang_versions))
            for rhel_version, golang_versions in golang_versions_by_rhel.items()
        }

    def csv_line(self, all_rhel_versions):
        out = [self.openshift]

        for rhel_version in all_rhel_versions:
            if rhel_version not in self.rhel_versions:
                out.append("")
            else:
                out.append(", ".join(self.golang_by_rhel_version[rhel_version]))

        return out


# Splits the incoming tag into its various sub-elements.
@dataclass
class SplitTag:
    rhel: str
    openshift: str
    golang_tag: str
    golang: str

    @classmethod
    def FromString(cls, version_str: str):
        split = version_str.split("-")
        keys = set(["rhel", "golang", "openshift"])
        found = {}
        for i, item in enumerate(split):
            if item in keys and split[i + 1] not in keys:
                found[item] = split[i + 1]

        if "golang" in found:
            found["golang_tag"] = found["golang"]
        else:
            found["golang_tag"] = ""

        # Get the Golang version from the image metadata.
        found["golang"] = get_full_go_version_from_image_metadata(version_str)

        return SplitTag(**found)

    @property
    def ocp_minor_version(self):
        return int(self.openshift.split(".")[1])


def get_full_go_version_from_image_metadata(version_str):
    metadata = get_image_metadata(version_str)

    # Prefer the GO_VERSION value in the env var section of the metadata
    for env in metadata["Env"]:
        if "GO_VERSION" in env:
            return env.replace("GO_VERSION=", "").replace("v", "")

    # Fall back to the url label and extract the Go version from there.
    return os.path.basename(metadata["Labels"]["url"]).split("-")[0].replace("v", "")


def load_tags():
    split_tags_by_ocp_version = defaultdict(list)
    all_rhel_versions = set()
    all_golang_versions = set()

    tags = get_builder_image_tags()

    # Split each tag while grouping it by its OCP version
    for tag in tags["status"]["tags"]:
        raw_tag = tag["tag"]

        if not is_tag_match(raw_tag):
            continue

        print(f"Processing tag {raw_tag}")

        split_tag = SplitTag.FromString(raw_tag.strip())
        if split_tag.ocp_minor_version >= 10:
            split_tags_by_ocp_version[split_tag.openshift].append(split_tag)
            all_rhel_versions.add(split_tag.rhel)
            all_golang_versions.add(split_tag.golang)

    # Load each split tag into an OCP instance which knows how to group by
    # RHEL and Golang versions.
    ocp_versions = sorted(
        [OCP(grouped) for ocp_version, grouped in split_tags_by_ocp_version.items()],
        key=lambda x: x.openshift,
    )

    all_rhel_versions = sorted(list(all_rhel_versions))
    all_golang_versions = sorted(list(all_golang_versions))

    return ocp_versions, all_rhel_versions, all_golang_versions


def get_image_metadata(raw_tag):
    args = [
        "skopeo",
        "inspect",
        "--no-tags",
        f"docker://registry.ci.openshift.org/ocp/builder:{raw_tag}",
    ]

    print(subprocess.list2cmdline(args))
    cmd = subprocess.run(args, capture_output=True)

    cmd.check_returncode()

    return json.loads(cmd.stdout)


def get_builder_image_tags():
    args = ["oc", "get", "imagestream/builder", "-n", "ocp", "-o", "json"]
    print(subprocess.list2cmdline(args))
    cmd = subprocess.run(args, capture_output=True)
    cmd.check_returncode()

    return json.loads(cmd.stdout)


def is_tag_match(tag):
    should_have = ["openshift", "rhel", "golang"]
    shouldnt_have = ["art", "multi", "preview"]

    for item in should_have:
        if item not in tag:
            return False

    for item in shouldnt_have:
        if item in tag:
            return False

    return True


ocp_versions, all_rhel_versions, all_golang_versions = load_tags()

output_filename = "builders.csv"

with open(output_filename, "w", newline="") as csvfile:
    writer = csv.writer(csvfile)

    headers = ["OpenShift Version"]
    headers.extend(
        [
            f"RHEL {rhel_version} Golang Builder Version(s)"
            for rhel_version in all_rhel_versions
        ]
    )

    writer.writerow(headers)
    for ocp in ocp_versions:
        writer.writerow(ocp.csv_line(all_rhel_versions))

    print(f"Wrote output to {output_filename}")
