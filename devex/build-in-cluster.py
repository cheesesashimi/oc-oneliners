#!/usr/bin/env python3

# This script is intended to improve the overall MCO developer experience
# (dev-ex) by leveraging the fact that one has a development cluster with
# powerful CPUs. Instead of doing a container image build locally on one's
# workstation / laptop and pushing it directly into their dev cluster, one
# commits their changes to a branch and pushes to their fork, then runs this
# script.
#
# This script does the following:
# 1. Identifies what your current Git branch is.
# 2. Identifies what your forked Git repository is. If it cannot do that, one
# can set GIT_FORK_URL with that info.
# 3. Creates an ImageStream and Image Build object that is configured to clone
# from your forked repo and branch.
# 4. Streams the build logs to your terminal.
# 5. Scales down the cluster version operator and machine config operator.
# 6. Patches the MCO images.json configmap, then patches each of the individual
# MCO components to point to the newly-built image.
# 7. Scales the machine config operator back up.

import json
import os
import pathlib
import shutil
import subprocess
import sys

MCO_REPO_ROOT="/Users/zzlotnik/go/src/github.com/openshift/machine-config-operator"
MCO_NAMESPACE="openshift-machine-config-operator"
GIT_FORK_URL="GIT_FORK_URL"
MAKEFILE_NAME = "Makefile.fast-build"
DOCKERFILE_NAME = "Dockerfile.fast-build"


class RepoContextManager(object):
    def __enter__(self):
        self._copy_file_to_repo_root(MAKEFILE_NAME)
        self._copy_file_to_repo_root(DOCKERFILE_NAME)

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._remove_file_from_repo_root(MAKEFILE_NAME)
        self._remove_file_from_repo_root(DOCKERFILE_NAME)
        print(f"RepoContextManager Exit State:\nexc_type: {exc_type}\nexc_value: {exc_value}\nexc_tb: {exc_tb}")

    def _copy_file_to_repo_root(self, file):
        src = os.path.join(pathlib.Path(__file__).parent.resolve(), file)
        dst = os.path.join(MCO_REPO_ROOT, file)
        print(f"Copying {src} to {dst}")
        shutil.copyfile(src, dst)

    def _remove_file_from_repo_root(self, file):
        target = os.path.join(MCO_REPO_ROOT, file)
        print(f"Removing {target}")
        os.remove(target)


# Returns the current git branch.
def get_git_branch():
    out = subprocess.run(["git", "branch", "--show-current"], capture_output=True)
    out.check_returncode()
    return out.stdout.decode("utf-8").strip()

# Converts the Git URL into an HTTPS Git URL for easy cloning. This takes
# git@github.com:cheesesashimi/machine-config-operator.git and converts it to
# https://github.com/cheesesashimi/machine-config-operator.git. There's a ton
# of edge-cases that this likely does not handle though :).
def convert_git_url(url):
    # First, we remove all of these things from our URL.
    to_strip = [
        "git://",
        "git@",
        "http://",
        "https://",
        "ssh://",
    ]

    for item in to_strip:
        url = url.replace(item, "")

    # Append an https:// onto our URL and replace any colons with slashes.
    return "https://" + url.replace(":", "/")

# Looks for the git forked URL in either GIT_FORK_URL or by looking at ones
# current Git state. We grab the first non-openshift Git remote we find when
# running git remote.
def get_git_remote():
    # If GIT_FORK_URL is set, convert that and use it.
    fork_url = os.getenv(GIT_FORK_URL)
    if fork_url:
        return convert_git_url(fork_url)

    # Otherwise, enumerate all of the git remotes and find the first
    # non-OpenShift remote.
    cmd = ["git", "remote"]
    out = subprocess.run(cmd, capture_output=True)
    out.check_returncode()
    remotes = out.stdout.decode("utf-8").strip().split("\n")
    for remote in remotes:
        cmd = ["git", "remote", "get-url", "--push", remote]
        remote_out = subprocess.run(cmd, capture_output=True)
        remote_out.check_returncode()
        output = remote_out.stdout.decode("utf-8").strip()
        if "openshift/machine-config-operator" not in output:
            return convert_git_url(output)

# Generates an ImageStream manifest for where to push the built MCO image to.
def get_mco_imagestream_spec():
    return {
        "apiVersion": "image.openshift.io/v1",
        "kind": "ImageStream",
        "metadata": {
            "name": "machine-config-operator",
            "namespace": MCO_NAMESPACE,
        },
        "spec": {
            "lookupPolicy": {
                "local": False,
            },
        },
    }

# Generates an OpenShift Image Build manifest, supplying the current git branch
# and remote fork.
def get_build_spec():
    # We override the repo Dockerfile because of
    # https://issues.redhat.com/browse/MCO-603. Once that is resolved, we can
    # remove this.
    dockerfile = """FROM registry.ci.openshift.org/ocp/builder:rhel-8-golang-1.19-openshift-4.13 AS builder
ARG TAGS=""
WORKDIR /go/src/github.com/openshift/machine-config-operator
COPY . .
# FIXME once we can depend on a new enough host that supports globs for COPY,
# just use that.  For now we work around this by copying a tarball.
RUN make install DESTDIR=./instroot && tar -C instroot -cf instroot.tar .

FROM registry.ci.openshift.org/ocp/4.13:base
ARG TAGS=""
COPY --from=builder /go/src/github.com/openshift/machine-config-operator/instroot.tar /tmp/instroot.tar
RUN cd / && tar xf /tmp/instroot.tar && rm -f /tmp/instroot.tar
COPY install /manifests

COPY templates /etc/mcc/templates
ENTRYPOINT ["/usr/bin/machine-config-operator"]
LABEL io.openshift.release.operator true
"""

    return {
        "apiVersion": "build.openshift.io/v1",
        "kind": "Build",
        "metadata": {
            "name": "mco-image-build",
            "namespace": MCO_NAMESPACE,
        },
        "spec": {
            "output": {
                "to": {
                    "kind": "ImageStreamTag",
                    "name": get_mco_imagestream_spec()["metadata"]["name"] + ":latest",
                }
            },
            "postCommit": {},
            "serviceAccount": "builder",
            "source": {
                # Delete this line once https://issues.redhat.com/browse/MCO-603 is resolved
                "dockerfile": dockerfile,
                "git": {
                    "uri": get_git_remote(),
                    "ref": get_git_branch(),
                },
                "type": "Dockerfile"
            },
            "strategy": {
                "dockerStrategy": {},
                "type": "Docker"
            }
        }
    }

# Deletes a given object and optionally checks the return code.
def delete_object(target, check_returncode=False, namespace=MCO_NAMESPACE):
    cmd = ["oc", "delete", "--namespace", namespace, target]
    out = subprocess.run(cmd)
    if check_returncode:
        out.check_returncode()

# Replaces a given object.
def replace_object(obj, namespace=MCO_NAMESPACE):
    cmd = ["oc", "replace", "--namespace", namespace, "--filename", "-"]
    subprocess.run(cmd, text=True, input=json.dumps(obj)).check_returncode()

# Patches a given object.
def patch_object(name, patch, namespace=MCO_NAMESPACE):
    cmd = ["oc", "patch", "--namespace", namespace, name, "--patch", json.dumps(patch)]
    subprocess.run(cmd).check_returncode()

# Applies a given object.
def apply_object(obj, namespace=MCO_NAMESPACE):
    cmd = ["oc", "apply", "--namespace", namespace, "--filename", "-"]
    subprocess.run(cmd, text=True, input=json.dumps(obj)).check_returncode()

# Gets an arbitrary object and deserializes it.
def get_object(obj, namespace=MCO_NAMESPACE):
    cmd = ["oc", "get", "--namespace", namespace, "--output", "json", obj]
    out = subprocess.run(cmd, capture_output=True)
    out.check_returncode()
    return json.loads(out.stdout)

# Determines if a given object exists. If so, it will deserialize it and return it. Otherwise, it will return None.
def has_object(obj, namespace=MCO_NAMESPACE):
    cmd = ["oc", "get", "--namespace", namespace, "--output", "json", obj]
    out = subprocess.run(cmd, capture_output=True)
    stderr = out.stderr.decode("utf-8")
    if "NotFound" in stderr or "the server doesn't have a resource type" in stderr:
        return None

    out.check_returncode()
    return json.loads(out.stdout)

# Scales a deployment in a given namespace
def scale_deployment(name, replicas, namespace=MCO_NAMESPACE):
    # Ensure that the deployment name is prefixed with the deployment object type.
    deployment_name = "deployment/" + name.replace("deploy/", "").replace("deployment/", "")
    replicas = str(replicas)
    cmd = ["oc", "scale", "--replicas", replicas, "--namespace", namespace, deployment_name]
    subprocess.run(cmd).check_returncode()

# Streams the build logs for the given target build.
def stream_build_logs(target, namespace=MCO_NAMESPACE):
    cmd = ["oc", "logs", "-f", "--namespace", namespace, target]
    return subprocess.run(cmd)

# Updates the images.json file in configmap/machine-config-operator-images to
# point to the new image.
def replace_mco_configmap(pullspec):
    configmap = get_object("configmap/machine-config-operator-images")

    # This data is in JSON format within the configmap, so we must deserialize it here...
    images_json = json.loads(configmap["data"]["images.json"])

    # ... make our changes here ...
    images_json["machineConfigOperator"] = pullspec

    # ... and serialize it here ...
    configmap["data"]["images.json"] = json.dumps(images_json)

    # ... before we can replace it in our cluster.
    replace_object(configmap)

# Patches the MCO component with the new image pullspec.
def patch_mco_component(component_name, component_type, image_pullspec):
    patch = {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": component_name,
                            "image": image_pullspec,
                            # This defaults to "IfNotPresent". When used with a
                            # tagged image pullspec (e.g., host/org/repo:tag)
                            # instead of an image digest pullspec (e.g.,
                            # host/org/repo@sha256), the Kubelet will not
                            # detect that a new image is present.
                            "imagePullPolicy": "Always",
                        }
                    ]
                }
            }
        }
    }

    target = component_type + "/" + component_name
    patch_object(target, patch)

# Restarts the MCO component. This is required for the MCO components to run
# the newly-built image.
def restart_mco_component(component_name, component_type):
    cmd = subprocess.run(["oc", "rollout", "restart", "-n", MCO_NAMESPACE, f"{component_type}/{component_name}"])
    cmd.check_returncode()

# Waits for the target build to complete.
def wait_for_build_to_complete(target):
    # By streaming the logs and looking at the return code, we can get an idea
    # of whether the build was successful. However, we also need to examine the
    # current build state since it is possible for the log streaming process to
    # fail independently of the build due to transient network issues.
    out = stream_build_logs(target)
    build = get_object(target)
    if out.returncode == 0 and build["status"]["phase"] == "Complete":
        return build

    # If our build is new, pending, or still running, we try again to stream
    # the logs and wait by calling this function again.
    if build["status"]["phase"] in frozenset(["New", "Pending", "Running"]):
        print("An error occurred while streaming the build logs. Retrying...")
        return wait_for_build_to_complete(target)

    # If our build failed or encountered an error, we dump as much info as we
    # can, then exit.
    if build["status"]["phase"] in frozenset(["Failed", "Error", "Cancelled"]):
        build_pod_target = "pod/" + build["metadata"]["annotations"]["openshift.io/build.pod-name"]
        print("There was an problem with the build:")
        verbs = ["get", "describe", "logs"]
        for item in [build_pod_target, target]:
            for verb in verbs:
                cmd = ["oc", verb, "--namespace", MCO_NAMESPACE, item]
                print("$", ' '.join(cmd))
                subprocess.run(cmd)
        sys.exit(1)

def add_git_branch_tag(pullspec):
    # Upon completion, create / update a tag with the Git branch. This can be
    # useful for ensuring when we're doing multiple things on the same dev
    # cluster across multiple Git branches.
    imagestream_name = get_mco_imagestream_spec()["metadata"]["name"]
    git_branch_tag = get_git_branch().replace("/", "_")
    subprocess.run(["oc", "tag", pullspec, f'{MCO_NAMESPACE}/{imagestream_name}:{git_branch_tag}']).check_returncode()


def start_mco_image_build_locally():
    env = os.environ
    env["podman"] = "docker"
    env["GOARCH"] = "amd64"
    env["GOOS"] = "linux"
    #tagged_pullspec = "image-registry.openshift-image-registry.svc:5000/openshift-machine-config-operator/machine-config-operator:latest"
    tagged_pullspec = "quay.io/zzlotnik/machine-config-operator:latest"

    cmd = subprocess.run(["make", "binaries"], env=env)
    cmd.check_returncode()

    cmd = subprocess.run(["docker", "build", "-t", tagged_pullspec, "--file", "Dockerfile.fast-build", "."], env=env)
    cmd.check_returncode()

    cmd = subprocess.run(["docker", "--config", "/Users/zzlotnik/.docker-zzlotnik-testing", "push", tagged_pullspec])
    cmd.check_returncode()

    cmd = subprocess.run(["docker", "inspect", tagged_pullspec], capture_output=True)
    cmd.check_returncode()
    results = json.loads(cmd.stdout)

    repo_digest = results[0]["RepoDigests"][0]
    imagestream_name = get_mco_imagestream_spec()["metadata"]["name"]
    imagestream_destination = f"{MCO_NAMESPACE}/{imagestream_name}:latest"

    # Tag the newly built / pushed image into the MCO ImageStream. This will
    # allow us to keep the same pullspec to avoid MachineConfig regeneration.
    cmd = subprocess.run(["oc", "tag", "--source=docker", repo_digest, imagestream_destination])
    cmd.check_returncode()

    git_branch_tag = get_git_branch().replace("/", "_")
    imagestream_destination = imagestream_destination.replace("latest", git_branch_tag)

    cmd = subprocess.run(["oc", "tag", "--source=docker", repo_digest, imagestream_destination])
    cmd.check_returncode()

    imagestream = get_object(f"imagestream/{imagestream_name}")
    pullspec = imagestream["status"]["dockerImageRepository"] + ":latest"

    return tagged_pullspec
    #return pullspec


# Determines if we can run our script.
def can_run():
    binaries = ["git", "oc"]
    for binary in binaries:
        if not shutil.which(binary):
            print(f"Did not find required binary '{binary}'")
            return False
        else:
            print(f"Found {binary}")

    # If we can't determine the git remote, fail.
    git_remote = get_git_remote()
    if not git_remote:
        print(f"No forked git remote found. Either add one or set '{GIT_FORK_URL}' and try again!")
        return False
    else:
        print(f"Using git remote: {git_remote}")

    # If KUBECONFIG is not set, fail.
    kubeconfig = os.getenv("KUBECONFIG")
    if not kubeconfig:
        print("KUBECONFIG not set!")
        return False
    else:
        print(f"KUBECONFIG set to {kubeconfig}")

    if not os.path.exists(kubeconfig):
        print("No KUBECONFIG found at", kubeconfig)
        return False
    else:
        print(f"{kubeconfig} exists")

    # Attempt to get pods as a test that we have a working kubeconfig and oc
    # environment with the correct permissions.
    get_object("pods")
    print("All systems go!")

    return True

# Rolls out a given MCO pullspec to the MCO Deployments / DaemonSets.
def rollout_pullspec(pullspec):
    # Scale down the cluster version operator and the MCO to ensure they do not
    # ovewrite our image updates.
    scale_deployment("cluster-version-operator", 0, "openshift-cluster-version")
    scale_deployment("machine-config-operator", 0)

    # Replace the MCO image configmap with one containing the pullspec to our
    # newly-built image.
    replace_mco_configmap(pullspec)

    # Patch each of the deployment / daemonsets directly so we don't have to
    # wait for the operator to reconcile them.
    mco_components = {
        "daemonset": [
            "machine-config-server",
            "machine-config-daemon",
        ],
        "deployment": [
            "machine-config-operator",
            "machine-config-controller",
            "machine-os-builder",
        ],
    }

    for component_type, components in mco_components.items():
        for component_name in components:
            target = f'{component_type}/{component_name}'
            if not has_object(target):
                print(f"{target} not found, skipping...")
                continue
            patch_mco_component(component_name, component_type, pullspec)
            restart_mco_component(component_name, component_type)

    # Scale the MCO back up.
    scale_deployment("machine-config-operator", 1)


def main():
    if not can_run():
        sys.exit(1)

    # Create our ImageStream.
    apply_object(get_mco_imagestream_spec())

    # Starts the build process and gets the image pullspec.
    #pullspec = start_mco_image_build()
    with RepoContextManager() as repoctx:
        pullspec = start_mco_image_build_locally()
        rollout_pullspec(pullspec)
    # Rolls out the image pullspec.
    #
    # TODO: If used with a non-ImageStream pullspec (e.g., quay.io), we should
    # tag the pullspec into the ImageStream to avoid MachineConfig churn.

if __name__ == "__main__":
    os.chdir(MCO_REPO_ROOT)
    main()
