#!/bin/bash

# This script traverses the issue comments in a given org / repo / PR and
# scrubs comments such as `/test pj-rehearse` as these comments are solely used
# to trigger the CI system and are inherently disposable. They do, however,
# pollute the comment stream.

org="$1"
repo="$2"
pr="$3"

pr_path="repos/$org/$repo/pulls/$pr"
comments_url="$(gh api -H "Accept: application/vnd.github.v3+json" "$pr_path" | jq -r '.comments_url')"
comments_url="${comments_url/https\:\/\/api.github.com\//}"
echo "$comments_url"

for url in $(gh api -H "Accept: application/vnd.github.v3+json" "$comments_url" | jq -r '.[] | select(.user.login == "cheesesashimi") | select (.body == "/test pj-rehearse") | .url'); do
  url="${url/https\:\/\/api.github.com\//}"
  gh api \
    --method DELETE \
    -H "Accept: application/vnd.github.v3+json" \
    "$url"
done
