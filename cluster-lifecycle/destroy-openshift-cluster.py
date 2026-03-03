#!/usr/bin/env python3

from lib import utils

import os
import subprocess
import shutil

def destroy_openshift_cluster(flavor, arch):
  run_dir = utils.get_run_dir(flavor, arch)
  installer_path = os.path.join(run_dir, "openshift-install")
  if not os.path.exists(run_dir):
    print(f"{run_dir} does not exist, exiting")
    return

  if not utils.does_cluster_exist(run_dir):
    print(f"No files which indicate that a cluster is present have been found, exiting")
    return

  if not os.path.exists(installer_path):
    print(f"No installer found at {installer_path}. A cluster may not exist, exiting.")
    return

  subprocess.run([installer_path, "version"]).check_returncode()
  subprocess.run([installer_path, "--log-level=debug", "destroy", "cluster"]).check_returncode()

  release_image, release_image_file = utils.get_release_image_from_file(flavor, arch)
  preserve_certain_files = release_image and release_image_file


  # If we don't have the release image file, just blow away the directory.
  if not release_image_file:
    print(f"No release image file found, removing run dir {run_dir}")
    shutil.rmtree(run_dir)
    return

  files_to_preserve = set([release_image_file, installer_path])
  print(f"Release image file found, will preserve {files_to_preserve}")

  # Otherwise, we need to be slightly more surgical.
  top_level = os.walk(run_dir).__next__()
  for filename in top_level[2]:
    current = os.path.join(run_dir, filename)
    if release_image_file and current in files_to_preserve:
      print(f"Preserving {current}")
      continue

    print(f"Removing {current}")
    os.remove(current)

  for subdir in top_level[1]:
    current = os.path.join(run_dir, subdir)
    print(f"Removing {current}")
    shutil.rmtree(current)

def destroy_all_openshift_clusters():
  for arch in [utils.ARCH_AMD64, utils.ARCH_ARM64]:
    for flavor in [utils.OCP_FLAVOR, utils.OKD_FLAVOR, utils.OKD_SCOS_FLAVOR]:
      destroy_openshift_cluster(flavor, arch)
