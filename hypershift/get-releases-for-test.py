#!/usr/bin/env python3

import requests

# Get the latest release
results = requests.get("https://amd64.ocp.releases.ci.openshift.org/api/v1/releasestream/4.12.0-0.nightly/latest")
release_tag = results.json()["name"]
print("Found", release_tag)

# Get the older release to upgrade to this one from
results = requests.get("https://amd64.ocp.releases.ci.openshift.org/api/v1/releasestream/4.12.0-0.nightly/release/" + release_tag)
upgrades = results.json()["upgradesTo"]

max_successes = 0
index = 0
for i, upgrade in enumerate(upgrades):
    if upgrade["Success"] > max_successes:
        max_successes = upgrade["Success"]
        index = i

print("Will upgrade from", upgrades[index]["From"], "to", release_tag)
