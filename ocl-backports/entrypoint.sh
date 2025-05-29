#!/usr/bin/env bash

/usr/local/bin/fetch-prs-into-sqlite-db.py
/usr/local/bin/runqueries.sh "/usr/local/bin/queries" "/out" "/out"
