#!/bin/sh
set -eu

cleanup() {
    rc=$?
    ctx logger info "label_worker_nodes.sh exiting with code ${rc}"
    exit $rc
}
trap cleanup EXIT

ctx logger info "Worker node labeling started."

export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
export PATH="${PATH}:/var/lib/rancher/rke2/bin"

if ! command -v kubectl >/dev/null 2>&1; then
    ctx logger info "kubectl not found. Skipping worker labeling."
    exit 0
fi

# Discover agent nodes: all nodes that lack the control-plane role label
AGENT_NODES=$(kubectl get nodes \
    -l '!node-role.kubernetes.io/control-plane,!node-role.kubernetes.io/master' \
    -o jsonpath='{.items[*].metadata.name}' 2>/dev/null) || true

if [ -z "$AGENT_NODES" ]; then
    ctx logger info "No agent nodes found to label. Skipping."
    exit 0
fi

LABELED=0
for NODE in $AGENT_NODES; do
    ctx logger info "Labeling node ${NODE} as worker."
    kubectl label node "$NODE" node-role.kubernetes.io/worker=true --overwrite
    LABELED=$((LABELED + 1))
done

ctx logger info "Worker node labeling complete. Labeled ${LABELED} node(s)."
