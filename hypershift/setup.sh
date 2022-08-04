#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR/vars.sh"

# OpenShift Devs should target devcluster.openshift.com which already exists,
# making this step unnecessary. Nevertheless, it is included but commented out
# for posterity.
#
# aws route53 create-hosted-zone \
#   --name "$BASE_DOMAIN" \
#   --caller-reference "$(whoami)-$(date +'%Y-%m-%d')"

# If you're using the devcluster.openshift.com AWS account, you
# will need to recreate this bucket as it gets automatically
# deleted every 24 hours.
aws s3api create-bucket \
  --acl public-read \
  --bucket "$BUCKET_NAME" \
  --region "$REGION"

# Installs Hypershift onto your target cluster, which then becomes the management cluster.
hypershift install \
  --oidc-storage-provider-s3-bucket-name "$BUCKET_NAME" \
  --oidc-storage-provider-s3-credentials "$AWS_CONFIG_FILE" \
  --oidc-storage-provider-s3-region "$REGION"

# Creates a new hosted cluster within your management cluster.
"$SCRIPT_DIR/create-hosted-cluster.sh" "$(whoami)-hosted-cluster"
