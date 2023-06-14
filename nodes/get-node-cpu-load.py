#!/usr/bin/env python3

# Runs uptime on all of the nodes in a given cluster. Uses asyncio for faster
# processing.

import asyncio
import json
import subprocess

def get_role_from_node(node):
    for label in node["metadata"]["labels"].keys():
        if "node-role.kubernetes.io" in label:
            return label


async def run_uptime_command(node_name):
    cmd = f'oc debug node/{node_name} -- uptime'
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    return proc


async def async_main():
    out = subprocess.run(["oc", "get", "nodes", "-o=json"], capture_output=True)
    out.check_returncode()
    nodes = {node["metadata"]["name"]: node for node in json.loads(out.stdout)["items"]}

    procs = {}

    for node_name in nodes.keys():
        uptime_command = await run_uptime_command(node_name)
        procs[node_name] = uptime_command

    for node_name, proc in procs.items():
        stdout, stderr = await proc.communicate()
        role = get_role_from_node(nodes[node_name])

        print(f'[{node_name} - {role}]\n{stdout.decode()}')
        if proc.returncode != 0:
            print(f'[stderr]\n{stderr.decode()}')

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
