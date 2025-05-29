#!/usr/bin/env bash

set -xeuo

querypath="$1"
dbpath="$2"
outputpath="$3"

stat "$dbpath"

for queryfile in "$querypath"/*.sql; do
  outfile="${queryfile/.sql/.csv}"
  outfile="$(basename "$outfile")"
  outfile="$outputpath/$outfile"
  sqlite3 -csv -header "$dbpath/prs.db" "$(cat "$queryfile")" > "$outfile"
done
