#!/bin/bash

set -xe

rundir="$HOME/.openshift-installer"

if [ ! -f "$rundir/openshift-install"]; then
	echo "openshift-install binary not found, which means there should not be a cluster to destroy, exiting"
	exit 0
fi

if [ ! -f "$rundir/metadata.json" ]; then
	echo "metadata.json file not found, which means there should not be a cluster to destroy, exiting"
	exit 0
fi

cd "$rundir";
$rundir/openshift-install version;
$rundir/openshift-install --log-level=debug destroy cluster;
rm "$rundir/openshift-install";
rm "$rundir/.openshift_install.log";
