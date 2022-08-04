#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR/vars.sh"

cluster_name="$1"

hypershift create cluster aws \
  --name "$cluster_name" \
  --node-pool-replicas=3 \
  --base-domain "$BASE_DOMAIN" \
  --pull-secret "$REGISTRY_AUTH_FILE" \
  --aws-creds "$AWS_CONFIG_FILE" \
  --region "$REGION" \
  --generate-ssh

infra_id="$(oc get "$HOSTED_CLUSTER_TYPE/$cluster_name" -n "$CLUSTERS_NAMESPACE" -o jsonpath='{.spec.infraID}')"
infra_id_file="$PWD/$cluster_name-infra-id"
echo "$infra_id" > "$infra_id_file"
echo "Your hosted cluster '$cluster_name' has infra ID: $infra_id"
echo "The infra ID has been saved to: $infra_id_file"
