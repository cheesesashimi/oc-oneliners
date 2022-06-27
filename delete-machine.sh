#!/bin/bash

set -x

node_name="$1"

machine_id="$(oc get "node/$node_name" -o jsonpath='{.metadata.annotations.machine\.openshift\.io/machine}' | sed 's/openshift-machine-api\///g')"

oc delete --wait=false "machine/$machine_id" -n openshift-machine-api
oc delete --wait=false "node/$node_name"
