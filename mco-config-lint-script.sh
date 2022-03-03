#!/bin/bash

# Attempts to implement a shellcheck linter for the configs that live within the MCO repo, but are not owned by the MCO developers.
# Currently does not work so well for the templatized configs.

set -uo pipefail

# Gather all the YAML files which do not have Golang templates embedded within them.
non_templatized_script_files="$(rg -g "*.yaml" --files-without-match -F "{{" ./templates | xargs rg --files-with-matches -F '#!/bin/bash' | sort)"

for file in $non_templatized_script_files; do
  # Extract the path from the file
  script_file="$(yq eval '.path' "$file")"
  echo "----- In $script_file -----"

  # Extract the script and pipe it into shellcheck
  # https://github.com/koalaman/shellcheck
  yq eval '.contents.inline' "$file" | shellcheck -
  printf "\n"
done

read -r -d '' mock_data << EOM
{
  "LBConfig": {
    "LbPort": "8080",
    "ApiPort": "7070"
  },
  "NonVirtualIP": "127.0.0.1",
  "Network": {
    "MTUMigration": {
      "Machine": {
        "To": "a-machine"
      }
    }
  },
  "NetworkType": "OVNKubernetes",
  "Proxy": {
    "HTTPProxy": "127.0.0.2:8080",
    "HTTPSProxy": "127.0.0.3:8443",
    "NoProxy": ""
  },
  "Images": {
    "baremetalRuntimeCfgImage": "baremetal-runtime-cfg-image"
  },
  "DNS": {
    "Spec": {
      "BaseDomain": ".openshift"
    }
  }
}
EOM

echo "$mock_data" > "mock_data.json"

templatized_script_files="$(rg -g '*.yaml' --files-with-matches -F '{{' ./templates | xargs rg --files-with-matches -F '#!/bin/bash' | sort)"

for file in $templatized_script_files; do
  echo "----- In $file -----"
  gomplate -c '.=mock_data.json' -f "$file" -d '.=mock_data.json' \
    --plugin=onPremPlatformAPIServerInternalIP=./print.sh \
    --plugin=onPremPlatformIngressIP=./print.sh
  script_file="$(echo "$rendered" | yq eval '.path' -)"
  echo "----- In $script_file -----"
  echo "$rendered" | yq eval '.contents.inline' - | shellcheck -
  printf "\n"
done
