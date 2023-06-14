#!/bin/bash

# Sometimes, if a cluster node gets into a bad state, it can be advantageous to
# just delete the machine and alllow the machine-api to provision you a new one
# instead of trying to roll it back. This script does that as quickly as possible.

set -x

node_name="$1"
node_name="${node_name/node\//}"

machine_id="$(oc get "node/$node_name" -o jsonpath='{.metadata.annotations.machine\.openshift\.io/machine}')"
machine_id="${machine_id/openshift-machine-api\//}"

oc delete --wait=false "machine/$machine_id" -n openshift-machine-api
oc delete --wait=false "node/$node_name"
