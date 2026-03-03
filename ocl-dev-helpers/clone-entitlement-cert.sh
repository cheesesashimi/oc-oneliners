#!/usr/bin/env bash

set -xeuo

if oc get secret etc-pki-entitlement -n openshift-machine-config-operator; then
  oc delete secret/etc-pki-entitlement -n openshift-machine-config-operator
fi

oc create secret generic etc-pki-entitlement \
  --namespace "openshift-machine-config-operator" \
  --from-file=entitlement.pem=<(oc get secret/etc-pki-entitlement -n openshift-config-managed -o go-template='{{index .data "entitlement.pem" | base64decode }}') \
  --from-file=entitlement-key.pem=<(oc get secret/etc-pki-entitlement -n openshift-config-managed -o go-template='{{index .data "entitlement-key.pem" | base64decode }}')
