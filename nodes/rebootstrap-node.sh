#!/usr/bin/env bash

set -xeuo pipefail

node="$1"
namespace="openshift-machine-config-operator"
tmp="$(mktemp -d)"
config_filename="$node-desired-config.json"

# This can't be a simple label or field selector query, because reasons: https://github.com/kubernetes/kubernetes/issues/49387
desired_config="$(oc get "node/$node" -o yaml | yq '.metadata.annotations["machineconfiguration.openshift.io/desiredConfig"]' &)"
ssh_bastion_pod_name="$(oc get pods -n "openshift-machine-config-operator" -l='k8s-app=ssh-bastion' | grep "Running" | awk '{print $1;}' &)"
wait

oc get "mc/$desired_config" -o json > "$tmp/$config_filename"
oc cp "$tmp/$config_filename" "$ssh_bastion_pod_name:/tmp/$config_filename" -n "$namespace"
rm -rf "$tmp"
oc exec -it "$ssh_bastion_pod_name" -n "$namespace" -- /tmp/scripts/fix_node.sh "$node"
