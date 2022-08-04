#!/usr/bin/env bash

AWS_CONFIG_FILE="$HOME/.aws/credentials"
BASE_DOMAIN="devcluster.openshift.com"
BUCKET_NAME="$(whoami)-hypershift-bucket"
CLUSTERS_NAMESPACE="clusters"
HOSTED_CLUSTER_TYPE="hostedcluster.hypershift.openshift.io"
MANIFESTS_FILE="$PWD/hypershift-manifests.yaml"
REGION="us-east-1"
# If you wish to use a different set of registry pull credentials, change this
# to point to those creds.
REGISTRY_AUTH_FILE="$HOME/.docker/config.json"
