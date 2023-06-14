#!/usr/bin/env bash

# Cleans all of the OpenShift CI-specific contexts from my main Kubeconfig
# file.

for context in $(oc config get-contexts -o name | grep -i "ci-op-"); do
	oc config delete-context "$context";
done
