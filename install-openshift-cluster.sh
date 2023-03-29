#!/bin/bash

set -xe

rundir="$HOME/.openshift-installer"
amd64_release_stream="4-dev-preview"
arm64_release_stream="4.12.0-0.nightly-arm64"
max_retries=5
dockerconfig="$HOME/.creds/openshift-dockerconfig.json"

fetch_openshift_install() {
	arch="$1"
	release_stream="$2"

	if [ -f "$rundir/openshift-install" ]; then
		echo "Using preexisting openshift-install binary"
		return
	fi

	if [ -f "$rundir/.openshift_release" ]; then
		release="$(cat $rundir/.openshift_release)"
		echo ".openshift_release file found, contains: $release"
	else
		latest_release_url="https://$arch.ocp.releases.ci.openshift.org/api/v1/releasestream/$release_stream/latest"
		release="$(curl "$latest_release_url" | jq -r '.pullSpec')"
		echo ".openshift_release file not found, using $release from $latest_release_url"
	fi

	cd "$rundir"
	/usr/local/bin/oc adm release extract --registry-config="$dockerconfig" --command=openshift-install "$release";
}

prepare_install_config() {
	arch="$1"
	cp "$HOME/.creds/openshift-install-config-${arch}.yaml" "$rundir/install-config.yaml";
	PULL_SECRET="$(cat "$dockerconfig" | jq -c '{auths}')" /usr/local/bin/yq eval '.pullSecret = strenv(PULL_SECRET)' -i "$rundir/install-config.yaml";
	SSH_KEYS="$(cat $HOME/.creds/workstation-ssh.pub $HOME/.ssh/id_ed25519.pub)" /usr/local/bin/yq eval '.sshKey = strenv(SSH_KEYS)' -i "$rundir/install-config.yaml";
}

install_openshift_cluster() {
	arch="$1"
	release_stream="$2"
	if [ -f "$rundir/.vacation_mode" ]; then
		echo "In vacation mode, exiting"
		exit 0
	fi

	fetch_openshift_install "$arch" "$release_stream";
	prepare_install_config "$arch"
	cd "$rundir"
	$rundir/openshift-install version;
	$rundir/openshift-install --log-level=debug create cluster;
}

do_post_install_config() {
	echo "Performing post-install cluster configuration..."
	KUBECONFIG="$rundir/auth/kubeconfig" /usr/local/bin/oc apply -f "$HOME/.openshift-cluster-configs/"
}

for i in $(seq 1 "$max_retries"); do
	install_openshift_cluster "amd64" "${amd64_release_stream}"
	if [ $? -eq 0 ]; then
		echo "Successfully installed your cluster after $i attempt(s)"
		do_post_install_config
		exit 0
	fi	

	echo "Your cluster did not come up cleanly, will destroy and retry..."
	# Destroy the maligned cluster
	cd "$rundir"
	$rundir/openshift-install --log-level=debug destroy cluster
done
