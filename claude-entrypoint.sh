#!/usr/bin/env bash

set -euo pipefail

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "Error: tmux is not installed" >&2
    exit 1
fi

# Validate session name argument
if [ $# -eq 0 ]; then
    echo "Usage: $0 <session-name>" >&2
    exit 1
fi

SESSION_NAME="$1"

# Start tmux session
tmux new-session -d -s "$SESSION_NAME" 'claude'

claude mcp add --transport sse jira http://127.0.0.1:8080/sse
mkdir -p /home/claude/.config/claude-code
bash -c 'jq -n \
  --arg url "$JIRA_URL" \
  --arg user "$JIRA_USER" \
  --arg token "$JIRA_TOKEN" \
  "{
    mcpServers: {
      atlassian: {
        command: \"npx\",
        args: [\"mcp-atlassian\"],
        env: {
          JIRA_URL: \$url,
          JIRA_USERNAME: \$user,
          JIRA_API_TOKEN: \$token
        }
      }
    }
  }" > /home/claude/.config/claude-code/mcp.json'

# After detaching or session ends, poll until session no longer exists
while true; do
    if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        exit 0
    fi
    sleep 1
done
