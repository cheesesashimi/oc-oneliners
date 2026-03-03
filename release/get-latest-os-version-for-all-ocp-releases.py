#!/usr/bin/env python3

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

import json
import subprocess


@dataclass(unsafe_hash=True)
class OCPReleaseStream:
    major: int
    minor: int

    def __str__(self):
        return f"{self.major}.{self.minor}"


@dataclass
class OCPReleaseVersion:
    major: int
    minor: int
    patch: Optional[int] = None
    metadata: Optional[str] = None

    @classmethod
    def FromString(cls, raw_version: str):
        def split_version(v):
            print(v)
            split_v = v.split(".")
            if len(split_v) == 2:
                return {"major": int(split_v[0]), "minor": int(split_v[1])}

            return {
                "major": int(split_v[0]),
                "minor": int(split_v[1]),
                "patch": int(split_v[2]),
            }

        split = raw_version.split("-")
        version = split_version(split[0])
        if len(split) == 2:
            version["metadata"] = "-".join(split[1:])

        return OCPReleaseVersion(**version)

    def release_stream(self):
        return OCPReleaseStream(major=self.major, minor=self.minor)

    def __str__(self):
        if not self.metadata:
            return f"{self.major}.{self.minor}.{self.patch}"
        else:
            return f"{self.major}.{self.minor}.{self.patch}-{self.metadata}"

    @property
    def pullspec(self):
        version = self.__str__()
        return f"quay.io/openshift-release-dev/ocp-release:{version}-x86_64"

    def os_version_for_release(self):
        release_info = run_command_and_get_json_output(
            ["oc", "adm", "release", "info", "--output=json", self.pullspec]
        )

        version = release_info["displayVersions"]["machine-os"]["Version"]
        prefix = f"{self.major}{self.minor}"
        if not version.startswith(prefix):
            return version

        out = version.split(".")
        rhel_version = out[1]
        return f"{rhel_version[0]}.{rhel_version[1]}.{out[2]}"


def run_command_and_get_json_output(args):
    print(subprocess.list2cmdline(args))
    cmd = subprocess.run(args, capture_output=True)
    cmd.check_returncode()
    return json.loads(cmd.stdout)


def get_all_releaseversions():
    releasestream = run_command_and_get_json_output(
        [
            "curl",
            "https://amd64.ocp.releases.ci.openshift.org/api/v1/releasestreams/accepted",
        ]
    )

    releases_by_y_stream = defaultdict(list)
    # for release in releasestream["4-stable"]:
    for release in releasestream["4.22.0-0.ci"]:
        orv = OCPReleaseVersion.FromString(release)
        releases_by_y_stream[orv.release_stream()].append(orv)

    for y_stream, releases in releases_by_y_stream.items():
        releases_by_y_stream[y_stream].sort(key=lambda x: x.patch)

    return releases_by_y_stream


for y_stream, releases in get_all_releaseversions().items():
    if y_stream.minor >= 12:
        release = releases[-1]
        print(y_stream, releases[-1].pullspec)
        print(release.os_version_for_release())
