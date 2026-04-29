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
# 1. Run this script with workspace name (optional, defaults to "workspace")
#    followed by one or more host workdirs to mount.
# 2. The script will pull the image and run it in interactive mode,
#    setting up everything necessary for it to work.
# Example: ./enter-claude-skills-env.sh myworkspace /path/to/dir1 /path/to/dir2

set -xeuo

pullspec="quay.io/zzlotnik/toolbox:ai-helpers-fedora-44"
workspace="${1:-workspace}"
workspace="${workspace/claude-/}"
workspace="claude-${workspace}"

# Collect all remaining arguments as host workdirs
shift
host_workdirs=("$@")

if [[ ${#host_workdirs[@]} -eq 0 ]]; then
  echo "No host workdir provided"
  echo "Usage: $0 [workspace_name] <host_workdir1> [host_workdir2] ..."
  exit 1
fi

# Validate that all provided directories exist
for dir in "${host_workdirs[@]}"; do
  if [[ ! -d "$dir" ]]; then
    echo "Host workdir $dir does not exist"
    exit 1
  fi
done

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

  # Set the primary workdir to the first directory provided
  primary_workdir="${host_workdirs[0]}"

  podman_args=(
    --detach
    --rm
    --uidmap 1000:0:1
    --uidmap 0:1:1000
    --uidmap "$host_uid:1001:1"
    --name "$workspace"
    --network=host # Not sure why this is suddenly needed...
  )

  # Mount all provided workdirs
  for dir in "${host_workdirs[@]}"; do
    podman_args+=(--volume="$dir:/workdir/$(basename "$dir"):Z")
  done

  podman_args+=(
    --workdir="/workdir/$(basename "$primary_workdir")"
    --volume="$HOME/.config/gcloud:/home/claude/.config/gcloud:z,U"
    --volume="$HOME/Repos/oc-oneliners/claude-entrypoint.sh:/claude-entrypoint.sh:z"
    --env "CLAUDE_CODE_USE_VERTEX=1"
    --env "CLOUD_ML_REGION=global"
    --env "ANTHROPIC_VERTEX_PROJECT_ID=itpc-gcp-core-pe-eng-claude"
    --env "JIRA_URL=https://redhat.atlassian.net"
    --env "JIRA_USER=zzlotnik@redhat.com"
    --env "JIRA_API_TOKEN=$(cat "$HOME/.creds/zzlotnik-jira-cloud-api-key")"
    --env "GH_TOKEN=$(cat "$HOME/.creds/gh-readonly-token")"
    --entrypoint=/claude-entrypoint.sh
  )

  if podman container exists "jira-mcp-server"; then
    podman_args+=(--env "JIRA_MCP_SERVER=true")
  fi

  # Check for kubeconfig in all provided workdirs, use the first one found
  for dir in "${host_workdirs[@]}"; do
    if [[ -f "$dir/kubeconfig" ]]; then
      podman_args+=(
        --env KUBECONFIG=/kubeconfig
        --volume="$dir/kubeconfig:/kubeconfig:z"
      )
      break
    fi
  done

  podman_args+=(
    "$pullspec"
  )

  podman run "${podman_args[@]}" "$workspace"
fi

podman exec -it "$workspace" tmux attach-session -t "$workspace"
