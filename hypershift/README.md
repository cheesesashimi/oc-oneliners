# Hypershift

These scripts are dependent upon the Hypershift binary, whose installation
instructions may be found
[here](https://hypershift-docs.netlify.app/getting-started/).

## setup.sh

This script does the following:
- Creates an AWS S3 bucket.
- Installs Hypershift onto your target cluster, which becomes the management cluster.
- Creates a hosted cluster within your management cluster.

## teardown.sh

This script does the following:
- Interrogates your management cluster for all hosted cluster objects (`$ oc get clusters -n clusters`).
- Gets information about each hosted cluster.
- Destroys each hosted cluster it finds by using the Hypershift binary.

## create-hosted-cluster.sh

This script creates a hosted cluster within your management cluster. To use:
`$ create-hosted-cluster.sh 'my-hosted-cluster-name'`

## destroy-hosted-cluster.sh

This script deletes a hosted cluster within your management cluster. To use:
`$ destroy-hosted-cluster.sh 'my-hosted-cluster-name'`

This script will fetch the infra ID and base name from the hostedcluster object and pass it into the Hypershift destroy command.
