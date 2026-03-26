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

pullspec="quay.io/zzlotnik/toolbox:ai-helpers-fedora-43"
workspace="${1:-workspace}"
workspace="${workspace/claude-/}"
workspace="claude-${workspace}"
host_workdir="${2:-}"

if [[ -z "$host_workdir" ]]; then
  echo "No host workdir provided"
  exit 1
fi

if [[ ! -d "$host_workdir" ]]; then
  echo "Host workdir $host_workdir does not exist"
  exit 1
fi

if [[ ! -f "$HOME/.config/gcloud/application_default_credentials.json" ]]; then
  echo "$HOME/.config/gcloud/application_default_credentials.json does not exist, exiting"
  exit 1
fi

# "$HOME/Repos/oc-oneliners/start-jira-mcp-server.sh"

if ! podman container inspect "$workspace" &> /dev/null; then
  if [[ "$pullspec" != *"localhost"* ]]; then
    podman pull "$pullspec"
  fi

  host_uid="$(id -u)"

  podman_args=(
    --detach
    --rm
    --uidmap 1000:0:1
    --uidmap 0:1:1000
    --uidmap "$host_uid:1001:1"
    --name "$workspace"
    --network=host # Not sure why this is suddenly needed...
    --volume="$host_workdir:/workdir/$(basename "$host_workdir"):Z"
    --workdir="/workdir/$(basename "$host_workdir")"
    --volume="$HOME/.config/gcloud:/home/claude/.config/gcloud:z,U"
    --env "CLAUDE_CODE_USE_VERTEX=1"
    --env "CLOUD_ML_REGION=us-east5"
    --env "ANTHROPIC_VERTEX_PROJECT_ID=itpc-gcp-core-pe-eng-claude"
    --entrypoint=/bin/bash
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

  podman run "${podman_args[@]}" -c 'sleep infinity'
fi

# Start claude ina tmux session if one does not exist.
if ! podman exec -it "$workspace" tmux has-session -t "$workspace" 2>/dev/null; then
  podman exec -it "$workspace" tmux new-session -d -s "$workspace" 'claude'
fi

podman exec -it "$workspace" tmux attach-session -t "$workspace"
