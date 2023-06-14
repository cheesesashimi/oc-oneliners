#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR/vars.sh"

nodepool="$1"
command="$2"

for node in $("$SCRIPT_DIR/get-nodes-in-nodepool.sh" "$nodepool"); do
  printf "%s output:\n%s\n" "$node" "$(oc debug "node/$node" -- chroot /host /bin/bash -c "$command")" &
done
wait
