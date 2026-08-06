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
#
# Three backends are supported:
#   claude              - Claude Code via GCP Vertex AI
#   opencode-vertex     - OpenCode via GCP Vertex AI
#   opencode-modelscorp - OpenCode via Models Corp (APIcast) API keys
#                         API keys are read from ~/.creds/apikeys.txt
#                         (format: "provider-id apikey" one per line).
#                         Provider IDs are matched against those in
#                         ~/.creds/opencode.json and the corresponding env vars
#                         (as specified by {env:...} references in the config)
#                         are injected into the container via --env arguments.

# To use:
# 1. Specify the backend as the first argument.
# 2. Provide a workspace name.
# 3. Provide one or more host workdirs to mount.
# Example: ./start-ai-sandbox-session.sh claude myworkspace /path/to/dir1 /path/to/dir2
# Example: ./start-ai-sandbox-session.sh opencode-vertex myworkspace /path/to/dir1
# Example: ./start-ai-sandbox-session.sh opencode-modelscorp myworkspace /path/to/dir1

set -euo pipefail

usage() {
  echo "Usage: $0 <claude|opencode-vertex|opencode-modelscorp> [workspace_name] <host_workdir1> [host_workdir2] ..."
  exit 1
}

if [[ $# -lt 1 ]]; then
  usage
fi

backend="${1,,}"
shift

case "$backend" in
claude | opencode-vertex | opencode-modelscorp) ;;
*)
  echo "Unknown backend: '$backend'. Must be 'claude', 'opencode-vertex', or 'opencode-modelscorp'."
  usage
  ;;
esac

pullspec="quay.io/zzlotnik/toolbox:ai-helpers-fedora-44"
CONTAINER_HOME="/home/claude"
GCP_PROJECT_ID="itpc-gcp-core-pe-eng-claude"
GCP_VERTEX_REGION="global"

# Derive workspace name and prefix based on backend.
# If the next argument looks like a directory path (starts with / or ./), treat
# it as the first workdir and fall back to a default workspace name.
if [[ $# -ge 1 && "${1}" != /* && "${1}" != ./* ]]; then
  workspace="${1}"
  shift
else
  workspace="workspace"
fi

case "$backend" in
claude)
  workspace="${workspace/claude-/}"
  workspace="claude-${workspace}"
  ai_tool="claude"
  ;;
opencode-vertex)
  workspace="${workspace/opencode-/}"
  workspace="opencode-${workspace}"
  ai_tool="opencode"
  ;;
opencode-modelscorp)
  workspace="${workspace/opencode-modelscorp-/}"
  workspace="opencode-modelscorp-${workspace}"
  ai_tool="opencode"
  ;;
esac

# Collect all remaining arguments as host workdirs
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

# --- Backend-specific credential pre-flight ---
api_key_env_args=()

if [[ "$backend" == "claude" || "$backend" == "opencode-vertex" ]]; then
  if [[ ! -f "$HOME/.config/gcloud/application_default_credentials.json" ]]; then
    echo "$HOME/.config/gcloud/application_default_credentials.json does not exist, exiting"
    exit 1
  fi
else
  # opencode-modelscorp
  OPENCODE_CONFIG="$HOME/.creds/opencode.json"
  APIKEYS_FILE="$HOME/.creds/apikeys.txt"

  if [[ ! -f "$OPENCODE_CONFIG" ]]; then
    echo "$OPENCODE_CONFIG does not exist, exiting"
    exit 1
  fi

  if [[ ! -f "$APIKEYS_FILE" ]]; then
    echo "$APIKEYS_FILE does not exist, exiting"
    exit 1
  fi

  # Build a map of apicast-hostname-prefix -> env var name by parsing opencode.json.
  # The hostname prefix is the portion of the baseURL before "--apicast-production",
  # which matches the provider ID format used in apikeys.txt.
  declare -A provider_env_map
  while IFS=$'\t' read -r hostname_prefix env_var; do
    provider_env_map["$hostname_prefix"]="$env_var"
  done < <(jq -r '.provider | to_entries[] |
    [
      (.value.options.baseURL | split("--")[0] | ltrimstr("https://")),
      (.value.options.apiKey | match("\\{env:([^}]+)\\}") | .captures[0].string)
    ] | @tsv' "$OPENCODE_CONFIG")

  while IFS=' ' read -r provider_id api_key; do
    [[ -z "$provider_id" || "$provider_id" == \#* ]] && continue
    if [[ -n "${provider_env_map[$provider_id]+_}" ]]; then
      api_key_env_args+=(--env "${provider_env_map[$provider_id]}=${api_key}")
    else
      echo "Warning: no env var mapping found for provider '$provider_id', skipping" >&2
    fi
  done <"$APIKEYS_FILE"
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
    --env "JIRA_URL=https://redhat.atlassian.net"
    --env "JIRA_USER=zzlotnik@redhat.com"
    --env "JIRA_API_TOKEN=$(cat "$HOME/.creds/zzlotnik-jira-cloud-api-key")"
    --env "GH_TOKEN=$(cat "$HOME/.creds/gh-readonly-token")"
    --env "LANG=en_US.UTF-8"
    --env "LC_ALL=en_US.UTF-8"
    --env "AI_TOOL=${ai_tool}"
  )

  trust_anchor_dir_mounted=false
  trust_anchor_dir="/etc/pki/ca-trust/source/anchors"
  if [[ -d "/run/host/$trust_anchor_dir" ]]; then
    podman_args+=(--volume="/run/host/${trust_anchor_dir}:${trust_anchor_dir}:ro")
    trust_anchor_dir_mounted=true
  elif [[ -d "$trust_anchor_dir" ]]; then
    podman_args+=(--volume="${trust_anchor_dir}:${trust_anchor_dir}:ro")
    trust_anchor_dir_mounted=true
  fi

  # Backend-specific env vars, volume mounts, and options
  case "$backend" in
  claude)
    podman_args+=(
      --env "CLAUDE_CODE_USE_VERTEX=1"
      --env "CLOUD_ML_REGION=${GCP_VERTEX_REGION}"
      --env "ANTHROPIC_VERTEX_PROJECT_ID=${GCP_PROJECT_ID}"
      --volume="$HOME/.config/gcloud:${CONTAINER_HOME}/.config/gcloud:z,U"
    )
    ;;
  opencode-vertex)
    podman_args+=(
      --env "GOOGLE_CLOUD_PROJECT=${GCP_PROJECT_ID}"
      --env "VERTEX_LOCATION=${GCP_VERTEX_REGION}"
      --env "GOOGLE_APPLICATION_CREDENTIALS=${CONTAINER_HOME}/.config/gcloud/application_default_credentials.json"
      --volume="$HOME/.config/gcloud:${CONTAINER_HOME}/.config/gcloud:z,U"
    )
    ;;
  opencode-modelscorp)
    podman_args+=(
      --volume "$HOME/.creds/opencode.json:${CONTAINER_HOME}/.config/opencode/opencode.json:z,U,ro"
      "${api_key_env_args[@]}"
    )
    ;;
  esac

  # Conditionally mount ~/.config/gws if it exists
  if [[ -d "$HOME/.config/gws" ]]; then
    podman_args+=(--volume="$HOME/.config/gws:${CONTAINER_HOME}/.config/gws:z,U")
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

  if [[ "$trust_anchor_dir_mounted" == "true" ]]; then
    podman exec -u=root -it "$workspace" update-ca-trust
  fi

  sleep 1
fi

podman exec -it "$workspace" tmux attach-session -t "$workspace"
