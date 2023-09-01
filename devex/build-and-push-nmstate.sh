#!/usr/bin/env bash

base_image="registry.ci.openshift.org/ocp/4.14:base"
tag="quay.io/zzlotnik/machine-config-operator:nmstate-4.14"

docker pull  "$base_image"
docker build -t "$tag" --file=Dockerfile.nmstate .
docker --config "$HOME/.docker-zzlotnik-testing" push "$tag"
