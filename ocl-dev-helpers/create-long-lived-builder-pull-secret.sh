#!/usr/bin/env bash

secret_name="$1"

if oc get "secret/$secret_name" -n openshift-machine-config-operator; then
  echo "Preexisting long-lived builder secret \"$secret_name\" found, deleting..."
  oc delete "secret/$secret_name" -n openshift-machine-config-operator
fi

# Store this value in a local var for future use.
current_kubeconfig="$KUBECONFIG"

# Grab the external cluster URL from the provided KUBECONFIG.
cluster_url="$(yq '.clusters[0].cluster.server' "$KUBECONFIG")"

# Create a service account token with a 24-hour duration for the builder service
# account in the MCO namespace.
service_account_token="$(oc create token builder --duration=24h -n openshift-machine-config-operator)"

# Unset the KUBECONFIG env var so we don't mutate our kubeconfig.
unset KUBECONFIG

# Log into the Kube API server with the new service account token.
#
# NOTE: Depending on your setup, you may be prompted to answer yes or no about
# insecure connections.
echo "Doing cluster login now"
oc --loglevel=10 login --token="$service_account_token" --server="$cluster_url"

echo "Doing registry login now"
# Log into the internal image registry and save the config into a local file.
oc --loglevel=10 registry login --to="$PWD/builder-dockerconfig.json"

# Using our original KUBECONFIG, create an image registry secret within the MCO
# namespace called "long-lived-builder-secret".
KUBECONFIG="$current_kubeconfig" oc create secret docker-registry "$secret_name" --from-file=.dockerconfigjson="$PWD/builder-dockerconfig.json" -n openshift-machine-config-operator
