#!/bin/bash

role="$1"
nodes="$(oc get nodes --selector "node-role.kubernetes.io/$role=" -o json | jq -r -c)"
num_nodes="$(echo "$nodes" | jq -r '.items | length')"
index=$(( $RANDOM % $num_nodes ))
node="$(echo "$nodes" | jq --argjson index "$index" -r '.items[$index].metadata.name')"
echo "Targetting node/$node..."
oc debug "node/$node"
