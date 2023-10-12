# Creating an SSH Bastion Pod

**WARNING!!! THIS SHOULD NOT BE USED ON A PRODUCTION CLUSTER!!!**

## Introduction

While OpenShift goes to great lengths to not require SSH access to a given
cluster node, there are certain situations where SSH access is necessary. For
example, if a node is not connected to Kube API server, one will not be able to
schedule debug pods on it.

Rather than complicate the installation process unnecessarily, one can create
an SSH bastion pod that will allow one to SSH into all cluster nodes provided
that the cluster is up and serving.

## How do I do this?

1. Create a dedicated SSH keypair specifically for this purpose. This is recommended because you will be exposing both the public and private keys, so it is important that this key is only used for this cluster. While not *strictly* required, one can generate a SSH keypair for each sandbox cluster used. Run: `$ ssh-keygen -t ed25519 -f ./my-ssh-key -q -N ""`.
2. Add the public key (`my-ssh-key.pub`, in this case) to the `install-config.yaml` for your sandbox cluster.
3. Install your sandbox cluster.
4. Once your sandbox cluster is up, create a new Kube secret containing your private key: `$ oc create secret opaque ssh-bastion-private-key --from-file=id_ed25519=./my-ssh-key -n openshift-machine-config-operator`.
5. We need to create a pod containing an SSH client that we can use with our public / private keypair. To do that, apply the following deployment to your cluster:
    ```yaml
    ---
    apiVersion: apps/v1
    kind: Deployment
    metadata:
    name: ssh-bastion
    namespace: openshift-machine-config-operator
    labels:
        k8s-app: ssh-bastion
    spec:
    replicas: 1
    selector:
        matchLabels:
        k8s-app: ssh-bastion
    template:
        metadata:
        labels:
            k8s-app: ssh-bastion
        spec:
        containers:
        # This can be any image that has an SSH client built into it.
        - image: quay.io/zzlotnik/testing:ssh-debug-pod
            name: ssh-bastion-sleep
            env:
            - name: HOME
            command:
            - /bin/bash
            - -c
            - |-
            #!/usr/bin/env bash
            set -euo pipefail
            sleep infinity
            volumeMounts:
            - mountPath: /tmp/key
            name: ssh-bastion-private-key
        volumes:
        - name: ssh-bastion-private-key
            secret:
            secretName: ssh-bastion-private-key
            defaultMode: 384
            items:
            - key: id_ed25519
                path: id_ed25519
    ```

## To SSH into a given cluster node

1. First, you need the node name. This is the same name you would use for `$ oc get node/<name>`.
2. You'll also need the name of the SSH bastion pod: `$ oc get pods -n "openshift-machine-config-operator" -l='k8s-app=ssh-bastion' | grep "Running" | awk '{print $1;}'`
3. Next, you can do something like `$ oc exec -it '<ssh-bastion-pod-name>' -n openshift-machine-config-operator -- ssh -i /tmp/key/id_ed25519 "core@<nodename>"`.
4. Alternatively, you can use the following script to automate this process and a shell alias to make it work seamlessly:
    ```bash
    #!/usr/bin/env bash

    node="$1"
    namespace="openshift-machine-config-operator"
    # This can't be a simple label or field selector query, because reasons: https://github.com/kubernetes/kubernetes/issues/49387
    ssh_bastion_pod_name="$(oc get pods -n "openshift-machine-config-operator" -l='k8s-app=ssh-bastion' | grep "Running" | awk '{print $1;}')"
    oc exec -it "$ssh_bastion_pod_name" -n "$namespace" -- ssh -i /tmp/key/id_ed25519 "core@$node"
    ```

    Then you can do something like: `$ ./ssh-to-node.sh "<nodename>"`
