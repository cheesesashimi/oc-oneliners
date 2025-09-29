#!/usr/bin/env bash

# This script is the entrypoint for my Claude Code environment. It uses the AI
# workspace image that I build daily in GitHub Actions which contains Claude
# Code as well as my usual tool assortment. However, any image which contains
# the Claude Code CLI (along with any other desired tools) should work as well.
# My AI workspace image is a bit large, clocking in at around 5 GB as of this
# writing.
#
# I purposely do not use Toolbox for this as I don't want Claude to have
# unfettered access to my homedir. It will mount the provided host_workdir into
# the container under /workdir.
#
# This script will also conditionally check for the presence of a kubeconfig
# file in the workdir root and if one is found, will set the KUBECONFIG env var
# to point to it and mount it into the container.

# To use:
# 1. Modify the host_workdir variable to point at the desired directory on your
#    host. I do not recommend pointing it at your homedir root.
# 2. Run this script which will pull the image and run it in interactive mode,
#    setting up everything necessary for it to work.

set -xeuo

pullspec="quay.io/zzlotnik/toolbox:ai-workspace-fedora-42"
host_workdir="$HOME/Repos/second-mco-clone"

if [[ ! -f "$HOME/.config/gcloud/application_default_credentials.json" ]]; then
  echo "$HOME/.config/gcloud/application_default_credentials.json does not exist, exiting"
  exit 1
fi

podman pull "$pullspec"

podman_args=(
  --interactive
  --tty
  --rm
  --name="claude-workspace"
  --volume="$host_workdir:/workdir:z"
  --workdir="/workdir"
  --env "CLAUDE_CODE_USE_VERTEX=1"
  --env "CLOUD_ML_REGION=us-east5"
  --env "ANTHROPIC_VERTEX_PROJECT_ID=itpc-gcp-core-pe-eng-claude"
  --volume="$HOME/.config/gcloud:/gcloud:z"
  --env "GOOGLE_APPLICATION_CREDENTIALS=/gcloud/application_default_credentials.json"
)

if [[ -f "$host_workdir/kubeconfig" ]]; then
  podman_args+=(
    --env KUBECONFIG=/kubeconfig
    --volume="$host_workdir/kubeconfig:/kubeconfig:z"
  )
fi

podman_args+=(
  "$pullspec"
)

podman run "${podman_args[@]}"
