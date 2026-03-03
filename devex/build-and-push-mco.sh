#!/usr/bin/env bash

authfile="$HOME/.creds/zzlotnik-quay-push-creds.json"
pullspec="quay.io/zzlotnik/machine-config-operator:latest"
#
# This is my usual MCO workspace
repo="$HOME/Repos/machine-config-operator"

# This is the MCO workspace I used for claude code refactoring
#repo="$HOME/Repos/openshift/machine-config-operator"

#mco-builder local --build-mode=normal --direct --repo-root "$HOME/Repos/machine-config-operator"
mco-builder local --final-image-pullspec "$pullspec" --push-secret "$authfile" --repo-root "$repo"
