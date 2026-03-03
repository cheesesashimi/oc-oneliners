#!/usr/bin/env bash

oc get imagestreams -n openshift-machine-config-operator -l 'machineconfiguration.openshift.io/used-by-e2e-test=' -o name | xargs oc delete &
oc get secrets -n openshift-machine-config-operator -l 'machineconfiguration.openshift.io/used-by-e2e-test=' -o name | xargs oc delete -n openshift-machine-config-operator &
oc get configmaps -n openshift-machine-config-operator -l 'machineconfiguration.openshift.io/used-by-e2e-test=' -o name | xargs oc delete -n openshift-machine-config-operator &
oc get namespaces -l 'machineconfiguration.openshift.io/used-by-e2e-test=' -o name | xargs oc delete &
oc get secrets -n openshift-machine-config-operator -l 'machineconfiguration.openshift.io/on-cluster-layering=' -o name | xargs oc delete -n openshift-machine-config-operator &
oc get configmaps -n openshift-machine-config-operator -l 'machineconfiguration.openshift.io/on-cluster-layering=' -o name | xargs oc delete -n openshift-machine-config-operator &
oc get machineosconfigs -o name | xargs oc delete &
oc get machineosbuilds -o name | xargs oc delete &
wait
