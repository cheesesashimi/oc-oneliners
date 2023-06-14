#!/usr/bin/env bash

release_repo="$HOME/Repos/openshift/release"

find "$release_repo/ci-operator/config/openshift" -type f -name "*[Oo][Kk][Dd]*.yaml" -exec yq '[{"filename": filename, "tests":[.tests[].as]} | select(.tests | length > 0)] | select(. | length > 0)' {} \;
