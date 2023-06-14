#!/usr/bin/env python3

# Reads a given JSON or YAML file from the command line and does the following:
# 1. Converts the input into JSON and pretty-prints the JSON using yq.
# 2. Compacts the JSON using jq.
# 3. Converts the input into YAML.
# 4. Compresses then base64-encodes the compressed bytes.
# 5. Analyzes the size of all the above before and after compression.

import base64
import gzip
import subprocess
import sys

# https://stackoverflow.com/questions/1094841/get-human-readable-version-of-file-size
def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"

def compute_lengths(input_bytes):
    raw = len(input_bytes)
    compressed_bytes = gzip.compress(input_bytes)
    compressed_and_encoded_bytes = base64.b64encode(compressed_bytes)
    compressed_size = len(compressed_bytes)
    compressed_and_encoded_size = len(compressed_and_encoded_bytes)

    out = {
        "Raw": raw,
        "Compressed": compressed_size,
        "Compressed and Encoded": compressed_and_encoded_size,
        "Compressed Savings": compressed_size / raw,
        "Compressed and Encoded Savings": compressed_and_encoded_size / raw
    }

    formatted = {}
    size_fields = ["Raw", "Compressed", "Compressed and Encoded"]
    for field in size_fields:
        formatted[field] = sizeof_fmt(out[field])

    #percent_fields = ["Compressed Savings", "Compressed and Encoded Savings"]
    #for field in percent_fields:
    #    formatted[field] = "{: .2f}%".format(out[field] * 100)

    return {
        "raw": out,
        "formatted": formatted
    }

def get_size_detail_line(sizes):
    lines = ('- %s: %s' % (name, item) for name, item in sizes["formatted"].items())
    return '\n'.join(lines)

def analyze_file(filename):
    result = subprocess.run(["yq", "-o=json", "--prettyPrint", filename], stdout=subprocess.PIPE)

    result = subprocess.run(["jq", "-r"], input=result.stdout, stdout=subprocess.PIPE)
    pretty_json = result.stdout

    result = subprocess.run(["jq", "-r", "-c"], input=pretty_json, stdout=subprocess.PIPE)
    compacted_json = result.stdout

    result = subprocess.run(["yq", "-o=yaml", "--prettyPrint"], input=pretty_json, stdout=subprocess.PIPE)
    yaml = result.stdout

    print("Input File:", filename)
    print("Pretty JSON ($ jq -r):")
    print(get_size_detail_line(compute_lengths(pretty_json)))
    print("Compacted JSON ($ jq -r -c):")
    print(get_size_detail_line(compute_lengths(compacted_json)))
    print("YAML ($ yq -o=yaml --prettyPrint):")
    print(get_size_detail_line(compute_lengths(yaml)))

files = sys.argv[1:]

for file in files:
    analyze_file(file)
    print("-" * 80)
