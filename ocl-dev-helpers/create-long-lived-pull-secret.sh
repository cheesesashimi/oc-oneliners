#!/usr/bin/env bash

secret_name="$1"
service_account_name="deployer"
namespace="openshift-machine-config-operator"

if oc get "secret/$secret_name" -n "$namespace"; then
  echo "Preexisting long-lived builder secret \"$secret_name\" found, deleting..."
  oc delete "secret/$secret_name" -n "$namespace"
fi

# Create a tempdir.
tmpdir="$(mktemp -d)"

# We need to temporarily override the KUBECONFIG path when we log into the
# builder service account.
service_account_kubeconfig_path="$tmpdir/kubeconfig"

# We also need a place to temporarily store the dockerconfig we generate before
# we can insert it as a secret.
builder_dockerconfig="$tmpdir/$service_account_name-dockerconfig.json"

# Grab the external cluster URL from the provided KUBECONFIG.
cluster_url="$(yq '.clusters[0].cluster.server' "$KUBECONFIG")"

# Create a service account token with a 24-hour duration for the builder service
# account in the MCO namespace.
service_account_token="$(oc create token $service_account_name --duration=24h -n openshift-machine-config-operator)"

# Log into the Kube API server with the new service account token. We override
# KUBECONFIG so that we don't mutate the currently active KUBECONFIG.
#
# NOTE: Depending on your setup, you may be prompted to answer yes or no about
# insecure connections.
KUBECONFIG="$service_account_kubeconfig_path" oc login --token="$service_account_token" --server="$cluster_url"

# Log into the internal image registry and save the config into a local file.
# We override the KUBECONFIG value because we need to do this as the service
# account user.
KUBECONFIG="$service_account_kubeconfig_path" oc registry login --to="$builder_dockerconfig"

# Now, with our original account, create an image registry secret within the
# MCO namespace.
oc create secret docker-registry "$secret_name" --from-file=.dockerconfigjson="$builder_dockerconfig" -n "$namespace"

# Finally, clean up after ourselves.
rm -rf "$tmpdir"
