#!/usr/bin/env bash

maybePullKubeconfig() {
  server_ip="192.168.68.73"
  if ping -c 1 -W 1 "$server_ip" &> /dev/null; then
    echo "Fetching KUBECONFIG"
    scp "zack@$server_ip":~/.openshift-installer/zzlotnik/auth/kubeconfig "$HOME/Repos/machine-config-operator"
  else
    echo "Server $server_ip unreachable; skipping KUBECONFIG retrieval"
  fi
}

maybePullNewImage() {
  container_name="$1"
  pullspec="$2"

  local_digest="$(podman image inspect --format '{{.Digest}}' "$pullspec")"
  remote="$(skopeo inspect "docker://$pullspec")"
  remote_digest="$(echo "$remote" | jq -r '.Digest')"
  created="$(echo "$remote" | jq -r '.Created')"

  if [ "$local_digest" == "$remote_digest" ]; then
    echo "Container image $container_name pullspec ($pullspec) up-to-date, skipping image pull"
  else
    podman pull "$pullspec"
  fi

  echo "Image $pullspec built on $created"
}

runStubContainer() {
  container_name="$1"
  pullspec="$2"

  time podman run -it --rm "$pullspec" echo "$container_name instantiated..."
}

recreate() {
  container_name="$1"
  pullspec="$2"

  if podman container exists "$container_name"; then
    podman stop "$container_name";
    podman rm "$container_name";
  fi

  time toolbox create --image "$pullspec" "$container_name"
}

updateAllImages() {
  declare -A workspaces

  workspaces[workspace]="quay.io/zzlotnik/toolbox:workspace-fedora-43"
  workspaces[rust-workspace]="quay.io/zzlotnik/toolbox:workspace-rust-fedora-43"
  workspaces[podman-dev-env]="quay.io/zzlotnik/toolbox:podman-dev-env"

  declare -A util_images
  util_images[gcloud]="gcr.io/google.com/cloudsdktool/google-cloud-cli:stable"
  util_images[aws]="public.ecr.aws/aws-cli/aws-cli"
  util_images[ai-helpers]="quay.io/zzlotnik/toolbox:ai-helpers-fedora-43"

  for util_image in "${!util_images[@]}"; do
    pullspec="${util_images[$util_image]}"
    maybePullNewImage "$util_image" "$pullspec"
  done

  for workspace in "${!workspaces[@]}"; do
    pullspec="${workspaces[$workspace]}"
    maybePullNewImage "$workspace" "$pullspec"
  done

  # for workspace in "${!workspaces[@]}"; do
  #   pullspec="${workspaces[$workspace]}"
  #   runStubContainer "$workspace" "$pullspec"
  # done

  if [[ -f /run/.containerenv ]]; then
    echo "Cannot recreate workspaces from within workspace container"
    exit 1
  fi

  for workspace in "${!workspaces[@]}"; do
    pullspec="${workspaces[$workspace]}"
    recreate "$workspace" "$pullspec" &
  done

  wait
}

main() {
  updateAllImages
  maybePullKubeconfig
}

main
