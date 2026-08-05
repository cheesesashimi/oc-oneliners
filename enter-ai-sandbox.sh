#!/usr/bin/env bash

# Unified entrypoint for Claude Code or OpenCode AI sandbox environments.
# Uses the AI workspace image built daily in GitHub Actions.
#
# I purposely do not use Toolbox for this as I don't want the AI to have
# unfettered access to my homedir. It will mount the provided host_workdir(s)
# into the container under /workdir.
#
# This script will also conditionally check for the presence of a kubeconfig
# file in the workdir root and if one is found, will set the KUBECONFIG env var
# to point to it and mount it into the container.

# To use:
# 1. Specify the AI tool as the first argument: "claude" or "opencode"
# 2. Provide a workspace name.
# 3. Provide one or more host workdirs to mount.
# Example: ./enter-ai-sandbox.sh claude myworkspace /path/to/dir1 /path/to/dir2
# Example: ./enter-ai-sandbox.sh opencode myworkspace /path/to/dir1

set -xeuo pipefail

usage() {
  echo "Usage: $0 <claude|opencode> [workspace_name] <host_workdir1> [host_workdir2] ..."
  exit 1
}

if [[ $# -lt 1 ]]; then
  usage
fi

ai_tool="${1,,}"
shift

case "$ai_tool" in
claude | opencode) ;;
*)
  echo "Unknown AI tool: '$ai_tool'. Must be 'claude' or 'opencode'."
  usage
  ;;
esac

pullspec="quay.io/zzlotnik/toolbox:ai-helpers-fedora-44"
CONTAINER_HOME="/home/claude"
GCP_PROJECT_ID="itpc-gcp-core-pe-eng-claude"
GCP_VERTEX_REGION="global"
workspace="${1:-workspace}"
workspace="${workspace/${ai_tool}-/}"
workspace="${ai_tool}-${workspace}"

# Collect all remaining arguments as host workdirs
shift
host_workdirs=("$@")

if [[ ${#host_workdirs[@]} -eq 0 ]]; then
  echo "No host workdir provided"
  usage
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

if ! podman container inspect "$workspace" &>/dev/null; then
  if [[ "$pullspec" != *"localhost"* ]]; then
    podman pull "$pullspec"
  fi

  # Set the primary workdir to the first directory provided
  primary_workdir="${host_workdirs[0]}"

  podman_args=(
    --detach
    --rm
    --privileged
    --uidmap 1000:0:1
    --uidmap 0:1:1000
    --uidmap 1001:1001:65536
    --gidmap 1000:0:1
    --gidmap 0:1:1000
    --gidmap 1001:1001:65536
    --name "$workspace"
    --network=host
    --workdir="/workdir/$(basename "$primary_workdir")"
    --volume="$HOME/.config/gcloud:${CONTAINER_HOME}/.config/gcloud:z,U"
    --env "JIRA_URL=https://redhat.atlassian.net"
    --env "JIRA_USER=zzlotnik@redhat.com"
    --env "JIRA_API_TOKEN=$(cat "$HOME/.creds/zzlotnik-jira-cloud-api-key")"
    --env "GH_TOKEN=$(cat "$HOME/.creds/gh-readonly-token")"
    --env "LANG=en_US.UTF-8"
    --env "LC_ALL=en_US.UTF-8"
    --env "AI_TOOL=${ai_tool}"
  )

  # Conditionally mount ~/.config/gws if it exists
  if [[ -d "$HOME/.config/gws" ]]; then
    podman_args+=(--volume="$HOME/.config/gws:${CONTAINER_HOME}/.config/gws:z,U")
  fi

  # Tool-specific environment variables and entrypoint
  if [[ "$ai_tool" == "claude" ]]; then
    podman_args+=(
      --env "CLAUDE_CODE_USE_VERTEX=1"
      --env "CLOUD_ML_REGION=${GCP_VERTEX_REGION}"
      --env "ANTHROPIC_VERTEX_PROJECT_ID=${GCP_PROJECT_ID}"
    )
  else
    podman_args+=(
      --env "GOOGLE_CLOUD_PROJECT=${GCP_PROJECT_ID}"
      --env "VERTEX_LOCATION=${GCP_VERTEX_REGION}"
      --env "GOOGLE_APPLICATION_CREDENTIALS=${CONTAINER_HOME}/.config/gcloud/application_default_credentials.json"
    )
  fi

  # Mount all provided workdirs
  for dir in "${host_workdirs[@]}"; do
    podman_args+=(--volume="$dir:/workdir/$(basename "$dir"):z")
  done

  registry_auth_file=""
  registry_auth_candidates=()

  if [[ -n "${REGISTRY_AUTH_FILE:-}" ]]; then
    registry_auth_candidates+=("$REGISTRY_AUTH_FILE")
  fi

  registry_auth_candidates+=(
    "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/containers/auth.json"
    "${DOCKER_CONFIG:-$HOME/.docker}/config.json"
    "$HOME/.config/containers/auth.json"
    "$HOME/.docker/config.json"
  )

  for candidate in "${registry_auth_candidates[@]}"; do
    if [[ -f "$candidate" ]]; then
      registry_auth_file="$candidate"
      break
    fi
  done

  if [[ -n "$registry_auth_file" ]]; then
    podman_args+=(--volume="$registry_auth_file:${CONTAINER_HOME}/.docker/config.json:z")
  fi

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

  podman run "${podman_args[@]}" "$pullspec" "$workspace"
  sleep 1
fi

podman exec -it "$workspace" tmux attach-session -t "$workspace"
