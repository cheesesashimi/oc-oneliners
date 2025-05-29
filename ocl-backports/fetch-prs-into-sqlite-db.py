#!/usr/bin/env python3

from pathlib import Path

import json
import os
import sqlite3
import subprocess


# Iterate through each PR and shuffle the keys around accordingly.
def transform_prs(prs):
    for pr in prs:
        # Bring the merge commit SHA to the top-level of the dict.
        if "mergeCommit" in pr and pr["mergeCommit"]:
            pr["mergeCommit"] = pr["mergeCommit"]["oid"]

        # Get the paths for each of the files referenced in the PR and store
        # them as a JSON string.
        pr["files"] = json.dumps([file["path"] for file in pr["files"]])

        # Bring the authors' login to the top level of the dict.
        pr["author"] = pr["author"]["login"]

        # Ensure that any keys which are None are empty. This is so we can
        # query for empty strings as opposed to 'None'.
        for key in pr.keys():
            if pr[key] == None:
                pr[key] = ""

        yield pr


def fetch_pr_commits_from_github(pr_number):
    result = subprocess.run(
        ["gh", "pr", "view", "--json", "commits", pr_number], capture_output=True
    )
    print(result.stderr)
    result.check_returncode()
    return json.loads(result.stdout)


# Fetches the PRs from GitHub and stores the JSON blob in a file.
def fetch_prs_from_github(filename):
    # The GitHub CLI requires one to specify which fields they're interested
    # in. So we do that here.
    fields = [
        "author",
        "files",
        "url",
        "title",
        "body",
        "isDraft",
        "number",
        "state",
        "createdAt",
        "baseRefName",
        "mergedAt",
        "mergeCommit",
    ]

    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "-s",
            "all",
            "-L",
            "400",
            "--repo",
            "openshift/machine-config-operator",
            "--json",
            ",".join(fields),
        ],
        capture_output=True,
    )
    result.check_returncode()
    print("PRs fetched from GitHub")
    with open(filename, "wb") as prs:
        prs.write(result.stdout)
        print(f"PRs stored in {filename}")


# Loads the JSON blob from the filesystem and transforms it into a format
# suitable for inssertion into a sqlite3 database.
def load_json(filename):
    with open(filename) as prs:
        print(f"Loading PRs from {filename}")
        return list(transform_prs(json.load(prs)))


# Determines if a file exists.
def file_exists(filename):
    p = Path(filename)
    return p.is_file() and not p.is_dir()


# Creates a sqlite3 database containing the commits retrieved from GitHub.
def create_sqlite_db(allprs):
    dbfilename = "prs.db"
    if file_exists(dbfilename):
        print(f"Found preexisting db file {dbfilename}, removing")
        os.remove(dbfilename)

    create_query = f"CREATE TABLE prs({", ".join(allprs[0].keys())})"

    con = sqlite3.connect(dbfilename)
    cur = con.cursor()
    cur.execute(create_query)

    # Get the first row so that we can get the keys from it.
    first = allprs[0]

    columns = ", ".join(first.keys())  # Get the column names from the dictionary keys
    placeholders = ", ".join(
        ["?"] * len(first)
    )  # Generate placeholders ('?') for each value

    query = f"INSERT INTO prs ({columns}) VALUES ({placeholders})"

    data = [tuple(pr.values()) for pr in allprs]
    cur.executemany(query, data)
    con.commit()
    print(f"{len(data)} PRs inserted into {dbfilename}")


# Fetches the JSON data from either GitHub or the JSON file on disk.
def get_json_from_file_or_github():
    filename = "prs.json"

    if file_exists(filename):
        return load_json(filename)

    fetch_prs_from_github(filename)
    return load_json(filename)


# Loads query results from a CSV file.
def load_query_results_from_file(filename):
    import csv

    with open(filename, newline="") as csvfile:
        return list(csv.DictReader(csvfile))


def get_pr_numbers_from_query_results():
    pr_numbers = []
    for result in load_query_results_from_file("mergedprsneedbackports.csv"):
        pr_numbers.append(
            result["url"].replace(
                "https://github.com/openshift/machine-config-operator/pull/", ""
            )
        )

    return pr_numbers


# Gets the commit SHAs for cherry-picking.
def get_all_commits_for_backporting():
    commits_to_cherrypick = []
    for pr_number in get_pr_numbers_from_query_results():
        commits = fetch_pr_commits_from_github(pr_number)
        shas = [commit["oid"] for commit in commits["commits"]]
        print(shas)
        commits_to_cherrypick += shas
    return commits_to_cherrypick


def main():
    create_sqlite_db(get_json_from_file_or_github())


if __name__ == "__main__":
    main()
