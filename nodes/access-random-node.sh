#!/bin/bash

set -xeuo

role="$1"
node="$(oc get nodes --selector "node-role.kubernetes.io/$role=" -o json | jq -r '.items[0].metadata.name')"
oc debug "node/$node"
