#!/usr/bin/env python3

import asyncio
import json
import subprocess
import time

RELEASE_PULLSPEC = "registry.ci.openshift.org/ocp/release@sha256:4ed2f88ca6bb339faf7bfcf6ab060e32ebe3dc5090e406f2b076c775b180c102"

def search_func(skopeo_output):
    return "nginx" in skopeo_output

def chunk_tags(in_list, size):
    for i in range(0, len(in_list), size):
        yield in_list[i:i+size]

def get_release(pullspec):
    cmd = subprocess.run(["oc", "adm", "release", "info", "-o=json", pullspec], capture_output=True)
    cmd.check_returncode()
    return json.loads(cmd.stdout)

async def run_skopeo(pullspec):
    cmd = f'skopeo inspect docker://{pullspec}'
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    return proc

async def async_main():
    release = get_release(RELEASE_PULLSPEC)

    # Organize our tags by tag name for easy lookup later.
    tags_by_name = {tag["name"]: tag
                    for tag in release["references"]["spec"]["tags"]}

    # Store each of our async processes so we can individually wait for them to
    # complete.
    procs = {}

    # We chunk the tags by 20 so we can wait for a quarter-second while they
    # finish. Without this, we end up having too many open files.
    for chunked_tags in chunk_tags(list(tags_by_name.values()), 20):
        # For each tag, call skopeo to get their data and store the async
        # process in our procs dict.
        for tag in chunked_tags:
            skopeo_command = await run_skopeo(tag["from"]["name"])
            procs[tag["name"]] = skopeo_command
        time.sleep(0.2)

    # For each of our async processes, get their output and call our search
    # func on it.
    for name, proc in procs.items():
        stdout, stderr = await proc.communicate()

        if search_func(stdout.decode()):
            print(f'found in {name} with pullspec {tags_by_name[name]["from"]["name"]}')

        if proc.returncode != 0:
            print(f'[stderr]\n{stderr.decode()}')

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
