#!/usr/bin/env bash

jira_mcp_server="jira-mcp-server"
jira_mcp_server_image="ghcr.io/sooperset/mcp-atlassian:latest"

if ! podman container inspect "$jira_mcp_server" &> /dev/null; then
  podman pull "$jira_mcp_server_image";

  podman run \
    --detach \
    --tty \
    --name "$jira_mcp_server" \
    --rm \
    --uidmap 1000:0:1 \
    --uidmap 0:1:1000 \
    --uidmap "$(id -u):1001:1" \
    -p 8080:8080 \
    --env "JIRA_SSL_VERIFY" \
    --env "JIRA_URL=https://issues.redhat.com" \
    --env "JIRA_PERSONAL_TOKEN=$(cat /home/zzlotnik/.creds/rh-jira-pat)" \
    "$jira_mcp_server_image" \
      --read-only \
      --transport sse \
      --port 8080 \
      -vv
fi
