#!/usr/bin/env bash

# This script creates a tmux session with multiple windows populated with oc
# watchers. Useful for quickly examining many different facets of a live
# OpenShift cluster.

set -xeuo pipefail

if [ -z "$KUBECONFIG" ]; then
  echo "No \$KUBECONFIG found!"
  exit 1
fi

cluster_name="$(yq '.clusters[0].name' "$KUBECONFIG" &)"
mco_pod_names="$(oc get pods -n openshift-machine-config-operator -o name &)"
cluster_version_operator_pod_name="$(oc get pods -n openshift-cluster-version -l=k8s-app=cluster-version-operator -o name &)"
wait

session="$cluster_name"

if tmux has-session -t "=$session" 2> /dev/null; then
  echo "Found preexisting session: $session. Killing and recreating"
  tmux kill-session -t "$session"
fi

window="mco-kube-objects"
tmux new-session -d -e KUBECONFIG="$KUBECONFIG" -s "$session" -n "$window" 'watch -n1 oc get mcp'
tmux set-option remain-on-exit on
tmux split-window -d -t "=$session:=$window" 'watch -n1 oc get mc'
tmux split-window -d -t "=$session:=$window" 'watch -n1 oc get nodes'
tmux split-window -d -t "=$session:=$window" "watch -n1 $HOME/go/src/github.com/openshift/machine-config-operator/hack/get-mcd-nodes.py"

#tmux new-window -d -t "=$session" -n "pods" 'watch -n1 oc get pods -n openshift-machine-config-operator' &
#tmux split-window -d -t "=$session:=pods" 'watch -n1 oc get pods -n openshift-cluster-node-tuning-operator'
#
#tmux new-window -d -t "=$session" -n "machine-api-objects" 'watch -n1 oc get machinesets -n openshift-machine-api' &
#tmux split-window -d -t "=$session:=machine-api-objects" 'watch -n1 oc get machines -n openshift-machine-api'

for pod_name in $mco_pod_names; do
  tmux new-window -d -t "=$session" -n "${pod_name/\/pod//}" "oc logs -f '$pod_name' -n openshift-machine-config-operator" &
done
wait

cluster_version="cluster-version"
tmux new-window -d -t "=$session" -n "$cluster_version" 'watch -n1 oc get clusteroperators'
tmux split-window -d -t "=$session:=$cluster_version" 'watch -n1 oc get clusterversion'
tmux split-window -d -t "=$session:=$cluster_version" 'oc logs -f -n openshift-cluster-version' "$cluster_version_operator_pod_name"

if [ -n "${TMUX:-}" ]; then
  tmux attach-session -t "$session"
fi
