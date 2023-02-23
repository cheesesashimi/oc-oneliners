#!/usr/bin/env python3

# This runs in the OpenShift CLI container

import os
import json
import subprocess
import shutil
import sys


def oc_login():
    serviceaccount_secrets_dir = "/var/run/secrets/kubernetes.io/serviceaccount"
    token = ""
    with open(os.path.join(serviceaccount_secrets_dir, "token"), "r") as token_file:
        token = token_file.read().strip()

    out = subprocess.run([
        shutil.which("oc"),
        "login",
        "%s:%s" % (os.getenv("KUBERNETES_SERVICE_HOST"), os.getenv("KUBERNETES_SERVICE_PORT")),
        "--token", token,
        "--certificate-authority", os.path.join(serviceaccount_secrets_dir, "ca.crt")
    ], env=os.environ)

    out.check_returncode()


def get_hostedclusters():
    out = subprocess.run([
            shutil.which("oc"),
            "get",
            "hostedclusters",
            "--all-namespaces",
            "-o=json"
        ], stdout=subprocess.PIPE, env=os.environ)

    out.check_returncode()

    return json.loads(out.stdout)["items"]


def use_custom_control_plane_operator(hostedcluster, image):
    patch = {
        "metadata": {
            "annotations": {
                "hypershift.openshift.io/control-plane-operator-image": image,
            }
        }
    }

    print("Updating hostedcluster", hostedcluster["metadata"]["name"], "with", image)

    return subprocess.Popen([
        shutil.which("oc"),
        "patch",
        "hostedcluster/" + hostedcluster["metadata"]["name"],
        "--namespace", hostedcluster["metadata"]["namespace"],
        "--patch=" + json.dumps(patch),
        "--type=merge"
    ], env=os.environ)


def get_new_image():
    cmd = subprocess.run([
        shutil.which("oc"),
        "get",
        "deployment/image-update-watcher",
        "--namespace", "hypershift",
        "-o", "jsonpath=" + "{.spec.template.spec.initContainers[0].image}"
    ], env=os.environ, stdout=subprocess.PIPE)

    cmd.check_returncode()
    return cmd.stdout.decode("utf-8")


def main():
    print(sys.version)
    oc_login()
    new_image = get_new_image()
    hostedclusters = get_hostedclusters()

    if len(hostedclusters) == 0:
        print("No hostedclusters found, exiting!")
        sys.exit(0)

    cmds = [use_custom_control_plane_operator(hostedcluster, new_image)
            for hostedcluster in get_hostedclusters()]

    for cmd in cmds:
        cmd.wait()

    for cmd in cmds:
        if cmd.returncode != None:
            sys.exit(cmd.returncode)


if __name__ == "__main__":
    main()
