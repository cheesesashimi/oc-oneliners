#!/usr/bin/env python3

import os
import subprocess
import tempfile

def check_chmod(tmpdir, mode):
    path = os.path.join(tmpdir, "a-file")
    with open(path, "w") as fobj:
        fobj.write("hello world")
        fobj.close()

    os.chmod(path, mode)

    process = subprocess.Popen(["stat", "-x", path],
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    print(stdout)

modes = [
    0o0644,
    0o0755,
    0o1755,
    0o2755,
    0o4755,
    0o7755,
    0o7777,
]

for mode in modes:
    with tempfile.TemporaryDirectory() as tmpdir:
        check_chmod(tmpdir, mode)
