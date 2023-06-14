#!/usr/bin/env bash

# Inspired By: https://www.redhat.com/sysadmin/troubleshooting-terminating-namespaces

# Start the proxy as a background job
oc proxy &

# Store the proxy's PID
oc_pid="$!"

# Extract our data
file="hosted-cluster.json"
name="$(yq '.metadata.name' "$file")"

# Wait for the proxy to finish initializing
sleep 5;

# Make our request
curl -k -H "Content-Type: application/json" -X PUT --data-binary @"$file" "http://127.0.0.1:8001/api/v1/hostedclusters.hypershift.openshift.io/$name/finalize"

# Shutdown the proxy
kill "$oc_pid"
