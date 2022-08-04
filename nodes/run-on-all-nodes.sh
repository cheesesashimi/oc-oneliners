#!/usr/bin/env bash

command="$1"

for node in $(oc get nodes -o name); do
  printf "%s output:\n%s\n" "$node" "$(oc debug "$node" -- chroot /host /bin/bash -c "$command")" &
done
wait
