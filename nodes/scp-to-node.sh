#!/usr/bin/env bash

set -xeuo

node="$1"
src_path="$2"
dest_path="$3"

namespace="openshift-machine-config-operator"

# This can't be a simple label or field selector query, because reasons: https://github.com/kubernetes/kubernetes/issues/49387
ssh_bastion_pod_name="$(oc get pods -n "openshift-machine-config-operator" -l='k8s-app=ssh-bastion' | grep "Running" | awk '{print $1;}')"

# First, we copy the provided file to the bastion pod
tmp_dir_on_pod="$(oc exec -it "$ssh_bastion_pod_name" -n "$namespace" -- mktemp -d | tr -d '\r')"
pod_file_target="$tmp_dir_on_pod/file"
oc cp "$src_path" "$ssh_bastion_pod_name:$pod_file_target" -n "$namespace"
echo "$src_path copied to bastion pod under $pod_file_target"
oc exec -it "$ssh_bastion_pod_name" -n "$namespace" -- scp -i /tmp/key/id_ed25519 "$pod_file_target" "core@$node:$dest_path"
echo "Copied from bastion pod ($pod_file_target) to node $node at path $dest_path"
oc exec -it "$ssh_bastion_pod_name" -n "$namespace" -- rm -rf "$tmp_dir_on_pod"
echo "$pod_file_target removed from bastion pod"
