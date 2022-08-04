#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR/vars.sh"

# Get a list of hosted cluster names
hosted_clusters="$(oc get "$HOSTED_CLUSTER_TYPE" -n "$CLUSTERS_NAMESPACE" -o name)"

for hosted_cluster in ${hosted_clusters[@]}; do
  "$SCRIPT_DIR/destroy-hosted-cluster.sh" "$hosted_cluster"
done
