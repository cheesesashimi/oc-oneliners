#!/usr/bin/env python3

# This script does the following:
# 1. It retrieves job names from https://testgrid.k8s.io for OCP and OKD
# informing and blocking job groups for a given list of OCP / OKD versions.
# 2. Using regex, it looks for a subset of job names which have known
# similarities between OCP / OKD.
# 3. It groups these jobs together, keyed first by the OCP / OKD version, then
# by the OKD job name and outputs them as YAML, e.g.:
# '4.9':
#   periodic-ci-openshift-release-master-okd-4.9-e2e-aws:
#   - periodic-ci-openshift-release-master-ci-4.9-e2e-aws
#   - periodic-ci-openshift-release-master-nightly-4.9-e2e-aws
#   periodic-ci-openshift-release-master-okd-4.9-e2e-vsphere:
#   - periodic-ci-openshift-release-master-nightly-4.9-e2e-vsphere
#   periodic-ci-openshift-release-master-okd-4.9-e2e-vsphere-upi:
#   - periodic-ci-openshift-release-master-nightly-4.9-e2e-vsphere-upi

# If there is no OKD equivalent job name to correlate with, it will omit the OCP equivalents.

# Note: This script makes no attempt to validate that the jobs are in any way
# equivalent other than having similar names :).

from collections import defaultdict

import os
import re
import requests
import yaml

name_filters = {
    "e2e-aws": re.compile(r"periodic-ci-openshift-release.*e2e-aws$"),
    "e2e-vsphere": re.compile(r"periodic-ci-openshift-release.*e2e-vsphere$"),
    "e2e-vsphere-upi": re.compile(r"periodic-ci-openshift-release.*e2e-vsphere-upi$"),
    "upgrade": re.compile(r"periodic.ci.openshift-release.*((upgrade|aws)-(aws|upgrade))$"),
}

def get_job_names_for_group(groupname):
    result = requests.get("https://testgrid.k8s.io/{groupname}/summary".format(groupname=groupname))
    return list(result.json().keys())

def is_job_name(job_name):
    for name, name_filter in name_filters.items():
        if name_filter.match(job_name):
            return name

    return None

def group_job_names_by_filter_match(job_names):
    by_filter_name = defaultdict(list)
    for job_name in job_names:
        job_filter_name = is_job_name(job_name)
        if not job_filter_name:
            continue
        by_filter_name[job_filter_name].append(job_name)

    return by_filter_name

def correlate_jobs_for_ocp_version(version):
    job_group_names = [
        "redhat-openshift-ocp-release-{version}-blocking".format(version=version),
        "redhat-openshift-ocp-release-{version}-informing".format(version=version),
        "redhat-openshift-okd-release-{version}-blocking".format(version=version),
        "redhat-openshift-okd-release-{version}-informing".format(version=version),
    ]

    by_job_group_name = {}

    for job_group_name in job_group_names:
        by_job_group_name[job_group_name] = get_job_names_for_group(job_group_name)

    okd_jobs = group_job_names_by_filter_match(by_job_group_name[job_group_names[2]] + by_job_group_name[job_group_names[3]])
    ocp_jobs = group_job_names_by_filter_match(by_job_group_name[job_group_names[0]] + by_job_group_name[job_group_names[1]])

    # We only expect a single job name for each of the OKD filters since
    # they're what the regex is based on.
    okd_jobs = {filter_name: job_name[0] for filter_name, job_name in okd_jobs.items()}

    correlated_jobs = {}

    for filter_name, job_names in ocp_jobs.items():
        okd_job_name = okd_jobs.get(filter_name)
        if not okd_job_name:
            continue
        correlated_jobs[okd_job_name] = sorted(job_names)

    return correlated_jobs

by_version = {}

versions = [
    "4.8",
    "4.9",
    "4.10",
    "4.11",
]

for version in versions:
    by_version[version] = correlate_jobs_for_ocp_version(version)

print(yaml.dump(by_version))
