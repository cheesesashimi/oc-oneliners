#!/usr/bin/env bash

node="$1"
namespace="openshift-machine-config-operator"
# This can't be a simple label or field selector query, because reasons: https://github.com/kubernetes/kubernetes/issues/49387
ssh_bastion_pod_name="$(oc get pods -n "openshift-machine-config-operator" -l='k8s-app=ssh-bastion' | grep "Running" | awk '{print $1;}')"
oc exec -it "$ssh_bastion_pod_name" -n "$namespace" -- ssh -i /tmp/key/id_ed25519 "core@$node"
