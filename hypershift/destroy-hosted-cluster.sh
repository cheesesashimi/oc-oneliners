#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR/vars.sh"

cluster_name="$1"

# Adds "hostedcluster.hypershift.openshift.io" onto the cluster name if not
# already present so we can call this script from both the CLI as well as from
# the teardown.sh script.
if [[ ! $cluster_name == "$HOSTED_CLUSTER_TYPE"* ]]; then
  cluster_name="$HOSTED_CLUSTER_TYPE/$cluster_name"
fi

cluster="$(oc get "$cluster_name" -n "$CLUSTERS_NAMESPACE" -o json)"
infra_id="$(echo "$cluster" | jq -r '.spec.infraID')"
base_domain="$(echo "$cluster" | jq -r '.spec.dns.baseDomain')"
hosted_cluster_name="$(echo "$cluster" | jq -r '.metadata.name')"

hypershift destroy cluster aws \
  --name "$hosted_cluster_name" \
  --infra-id "$infra_id" \
  --base-domain "$base_domain" \
  --aws-creds "$AWS_CONFIG_FILE"
