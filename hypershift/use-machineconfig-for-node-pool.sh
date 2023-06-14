#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR/vars.sh"

nodepool_name="$1"
machineconfig_name="$2"

patch="$(mc="$machineconfig_name" yq e -n '.spec.config[0] = {"name": strenv(mc)}')"

oc patch \
  "nodepool/$nodepool_name" \
  --namespace "$CLUSTERS_NAMESPACE" \
  --patch="$patch" \
  --type=merge
