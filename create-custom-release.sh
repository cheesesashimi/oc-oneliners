#!/usr/bin/env bash

set -xeuo pipefail

# MUST USE BASE RELEASE IMAGE FROM CI REGISTRY!!
# This is because one must (theoretically) push to two different Quay accounts.
base_release_image="registry.ci.openshift.org/ocp/release:4.13.0-0.ci-2023-01-13-142357"

# TODO: Find these in rhcos-devel so that we can skip the skopeo copy step
rhel_coreos_8_override="quay.io/openshift-release-dev/ocp-v4.0-art-dev@sha256:7e5181599619e8c21e47336f687f94b2af162635fb0a44bcfbb7726560730441"
rhel_coreos_8_extensions_override="quay.io/openshift-release-dev/ocp-v4.0-art-dev@sha256:fcb1dfb2e6b945c3c14a45f619fc3f61e17273b4584559ea55346cf7f0c4657e"
machine_os_content_override="quay.io/openshift-release-dev/ocp-v4.0-art-dev@sha256:1a7280333a4f412e037fa025704646b65c7757f53650c1c3a30e792358058aa1"

quay_push_creds="$HOME/Downloads/zzlotnik-zzlotnik-workstation-push-auth.json"
export quay_push_creds_yaml="${quay_push_creds/json/yaml}"
docker_pull_creds="$HOME/.docker/config.json"
docker_pull_creds_yaml="${docker_pull_creds/json/yaml}"

# Copy these into my namespace so they can be referenced from elsewhere.
skopeo copy --src-authfile="$docker_pull_creds" --dest-authfile="$quay_push_creds" "docker://$rhel_coreos_8_override" "docker://quay.io/zzlotnik/testing:coreos"
skopeo copy --src-authfile="$docker_pull_creds" --dest-authfile="$quay_push_creds" "docker://$rhel_coreos_8_extensions_override" "docker://quay.io/zzlotnik/testing:coreos-extensions"
skopeo copy --src-authfile="$docker_pull_creds" --dest-authfile="$quay_push_creds" "docker://$machine_os_content_override" "docker://quay.io/zzlotnik/testing:machine-os-content-override"

#  Replace the Quay creds which enable pushing to my own namespace with the
#  ones that allow me to pull from the openshift-dev namespace.
yq -o=yaml --prettyPrint "$quay_push_creds" > "$quay_push_creds_yaml"
yq -o=yaml --prettyPrint "$docker_pull_creds" > "$docker_pull_creds_yaml"
yq -o=json '. *= load(strenv(quay_push_creds_yaml))' "$docker_pull_creds_yaml" | jq -r '{auths}' > $HOME/tmp-creds.json

# Create and push the release
oc adm release new \
  --registry-config="$HOME/tmp-creds.json" \
  --from-release "$base_release_image" \
  rhel-coreos-8="quay.io/zzlotnik/testing:coreos" \
  rhel-coreos-8-extensions="quay.io/zzlotnik/testing:coreos-extensions" \
  machine-os-content="quay.io/zzlotnik/testing:machine-os-content-override" \
  --to-image="quay.io/zzlotnik/testing:latest"

rm "$quay_push_creds_yaml" "$docker_pull_creds_yaml" "$HOME/tmp-creds.json"
