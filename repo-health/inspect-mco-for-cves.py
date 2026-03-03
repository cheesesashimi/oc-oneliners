#!/usr/bin/env python3

from dataclasses import dataclass

import contextlib
import os
import json
import subprocess
import time


@dataclass(unsafe_hash=True, order=True)
class ReleaseBranch:
    major: int
    minor: int

    @classmethod
    def FromString(cls, raw_branch_name):
        split = raw_branch_name.split("-")
        major, minor = split[1].split(".")
        return ReleaseBranch(major=int(major), minor=int(minor))

    @property
    def branch_name(self):
        return f"release-{self.major}.{self.minor}"

    def __str__(self):
        return self.branch_name


class Module(object):
    def __init__(self, repo, raw_path):
        self.repo = repo
        self.path = raw_path

    @property
    def name(self):
        return os.path.basename(self.path)

    @property
    def full_path_on_disk(self):
        return os.path.join(self.repo.path, self.path)

    def output_path(self, branch):
        return os.path.join(self.repo.debug_build_dir_for_branch(branch), self.name)

    def podman_build_command(self, branch):
        builder_images = self.repo.read_dockerfile()
        module_path = "/go/src/github.com/openshift/machine-config-operator"
        volume = f"{self.repo.path}:{module_path}"
        return [
            "podman",
            "run",
            "-it",
            "--rm",
            "--name",
            self.name,
            "-v",
            volume,
            "-w",
            self.full_path_on_disk.replace(self.repo.path, module_path),
            builder_images[0],
            "go",
            "build",
            "-o",
            self.output_path(branch).replace(self.repo.path, module_path),
        ]

    def build_command(self, branch):
        return ["go", "build", "-o", self.output_path(branch)]


class Repo(object):
    def __init__(self, path):
        self.path = path

    def change_branch(self, branch):
        os.chdir(self.path)
        subprocess.run(["git", "checkout", release_branch.branch_name], check=True)

    def find_all_main_modules(self):
        args = [
            "rg",
            "-g",
            "!vendor",
            "--files-with-matches",
            "-F",
            "func main(",
            "--json",
        ]
        print(subprocess.list2cmdline(args))
        cmd = subprocess.run(
            args,
            capture_output=True,
            text=True,
        )
        files = []
        for line in cmd.stdout.split("\n"):
            if not line:
                continue

            results = json.loads(line)
            if results["type"] == "match":
                files.append(results["data"]["path"]["text"])

        deduped = set(
            [
                os.path.dirname(file)
                for file in files
                if "devex" not in file and file != ""
            ]
        )

        return [Module(self, module) for module in deduped]

    def get_all_release_branches(self):
        os.chdir(self.path)

        cmd = subprocess.run(
            ["git", "branch", "--remote"],
            capture_output=True,
            text=True,
            check=True,
        )

        filtered_items = set(
            (
                ReleaseBranch.FromString(item.strip().split("/")[1])
                for item in cmd.stdout.split("\n")
                if "/release-4" in item
            )
        )

        return sorted(list(filtered_items))

    def debug_build_dir_for_branch(self, branch):
        return os.path.join(self.path, "debug_builds", branch.branch_name)

    def module_path(self, module):
        return os.path.join(self.path, module)

    def read_dockerfile(self):
        with open(os.path.join(self.path, "Dockerfile"), "r") as dockerfile:
            return [
                line.split(" ")[1]
                for line in dockerfile
                if line.startswith("FROM") and "builder" in line
            ]


repo_dir = "/home/zzlotnik/Scratchspace/claude-mco-workspace"

repo = Repo(repo_dir)

for release_branch in repo.get_all_release_branches():
    if release_branch.minor <= 10:
        continue
    repo.change_branch(release_branch)
    print(release_branch)

    gomodfilepath = os.path.join(repo.path, "go.mod")
    with open(gomodfilepath, "r") as gomodfile:
        for line in gomodfile:
            if "logrus" in line:
                print(release_branch, line)
                break

#    os.chdir(repo.path)

#    started_builds = {}

#    for module in repo.find_all_main_modules():
#        os.makedirs(repo.debug_build_dir_for_branch(release_branch), exist_ok=True)
#        os.chdir(module.full_path_on_disk)
#
#        build_args = module.podman_build_command(release_branch)
#        print(build_args)
#        print(subprocess.list2cmdline(build_args))
#        started_builds[module.name] = subprocess.Popen(build_args)
#
#    finished_builds = set()
#
#    while True:
#        for name, started_build in started_builds.items():
#            if started_build.poll() != None and name not in finished_builds:
#                print(f"{release_branch} - {name} finished")
#                finished_builds.add(name)
#
#        if finished_builds == set(started_builds.keys()):
#            print(f"All builds for {release_branch} done")
#            break
#
#        time.sleep(1)
