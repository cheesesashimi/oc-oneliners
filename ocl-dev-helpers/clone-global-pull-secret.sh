#!/usr/bin/env bash

if oc get secret global-pull-secret-copy -n openshift-machine-config-operator; then
  oc delete secret/global-pull-secret-copy -n openshift-machine-config-operator
fi

oc create secret docker-registry global-pull-secret-copy \
  --namespace "openshift-machine-config-operator" \
  --from-file=.dockerconfigjson=<(oc get secret/pull-secret -n openshift-config -o go-template='{{index .data ".dockerconfigjson" | base64decode}}')
