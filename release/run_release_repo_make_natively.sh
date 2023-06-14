#!/usr/bin/env bash

set -euox pipefail

release_config_root="$HOME/Repos/openshift/release"

cd "$release_config_root"

ci-operator-checkconfig \
  --config-dir ./ci-operator/config \
  --registry ./ci-operator/step-registry

ci-operator-prowgen \
  --from-dir ./ci-operator/config \
  --to-dir './ci-operator/jobs'

sanitize-prow-jobs \
  --config-path ./core-services/sanitize-prow-jobs/_config.yaml \
  --prow-jobs-dir './ci-operator/jobs'

determinize-ci-operator \
  --config-dir './ci-operator/config' \
  --confirm

cd core-services/prow/02_config && ./generate-boskos.py && cd "$release_config_root"

determinize-prow-config \
  --prow-config-dir ./core-services/prow/02_config \
  --sharded-prow-config-base-dir ./core-services/prow/02_config \
  --sharded-plugin-config-base-dir ./core-services/prow/02_config

generate-registry-metadata \
  --registry ./ci-operator/step-registry

template-deprecator \
  --prow-jobs-dir './ci-operator/jobs' \
  --prow-config-path './core-services/prow/02_config/_config.yaml' \
  --plugin-config './core-services/prow/02_config/_plugins.yaml' \
  --allowlist-path './core-services/template-deprecation/_allowlist.yaml'
