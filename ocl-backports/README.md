# ocl-backports

The script that is found within this directory was used to retrieve a set of PRs from GitHub and insert them into a sqlite3 database to determine which PRs should be assembled into the OCL 4.18 backport. The general idea is to run the script to create the sqlite3 database and then use the SQL queries to determine which PRs should be backported.

I've included a Containerfile which contains all necessary dependencies, including the Python3 runtime, sqlite3 and the GitHub CLI:
1. `podman build -t localhost/ocl-backports:latest`
2. `podman run -it --rm -v "$PWD:/out:Z" -e "GH_TOKEN=$your_github_cli_token" localhost/ocl-backports:latest`

The resulting CSVs and `prs.db` files will be stored in your current directory.
