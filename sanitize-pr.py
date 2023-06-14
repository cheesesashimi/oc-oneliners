#!/usr/bin/env python3

# Whenever I have a PR that I have to frequently trigger additional CI runs by
# using the OpenShift CI bot, this is useful for removing all of my garbage
# comments used to trigger certain CI workflows. This wraps the official GitHub
# CLI which does most of the heavy lifting.

import subprocess
import json

def delete_comment(comment):
    url = comment["url"].replace("https://api.github.com/", "")
    subprocess.run(["gh", "api", "--method", "DELETE", "-H", "Accept: application/vnd.github.v3+json", url])
    print("Deleted:", comment["body"])

def find_and_delete_comments(opts, username):
    comments_path = "repos/%(org)s/%(repo)s/issues/%(pr)s/comments" % opts
    comments_output = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github.v3+json", comments_path], capture_output=True)
    parsed = json.loads(comments_output.stdout)

    for comment in parsed:
        comment_body = comment["body"]
        commentor_username = comment["user"]["login"]

        if commentor_username == username and comment_body.startswith("/test"):
            delete_comment(comment)

if __name__ == "__main__":
    username = "cheesesashimi"

    opts = {
        "org": "openshift",
        "repo": "machine-config-operator",
        "pr": "3649",
    }

    prs = ["3649", "3637"]

    for pr in prs:
        opts["pr"] = pr
        find_and_delete_comments(opts, username)
