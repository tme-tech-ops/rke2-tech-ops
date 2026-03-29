#!/bin/sh
set -eu

cleanup() {
    rc=$?
    ctx logger info "env_postcheck.sh exiting with code ${rc}"
    exit $rc
}
trap cleanup EXIT

RKE2_RUNNING="false"
RKE2_NODE_STATUS="N/A"
RKE2_API_URL="N/A"
RKE2_JOIN_TOKEN="N/A"
RKE2_KUBECONFIG="N/A"

mgmt_ip=$(hostname -I | awk '{print $1}')

ctx logger info "Post install check started."

# Primary health check: verify rke2-server service is active (CP1 is always a server)
if systemctl is-active --quiet rke2-server 2>/dev/null; then
    ctx logger info "RKE2 server service is running."
    RKE2_RUNNING="true"
    RKE2_API_URL="https://${mgmt_ip}:6443"

    # Attempt to get node status
    export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
    export PATH="${PATH}:/var/lib/rancher/rke2/bin"
    if command -v kubectl >/dev/null 2>&1; then
        if kubectl wait --for=condition=Ready nodes --all --timeout=120s >/dev/null 2>&1; then
            RKE2_NODE_STATUS="Ready"
            ctx logger info "RKE2 cluster status: Ready"
        else
            RKE2_NODE_STATUS="NotReady"
            ctx logger info "RKE2 cluster status: NotReady"
        fi
    fi

    # Get join token if available
    if [ -f /var/lib/rancher/rke2/server/node-token ]; then
        RKE2_JOIN_TOKEN=$(cat /var/lib/rancher/rke2/server/node-token)
        ctx logger info "Captured join token."
    fi

    RKE2_KUBECONFIG="/etc/rancher/rke2/rke2.yaml"
else
    ctx logger info "RKE2 server service is not running on CP1."
fi

ctx logger info "Post install check completed."
ctx instance runtime-properties capabilities.rke2_running "${RKE2_RUNNING}"
ctx instance runtime-properties capabilities.rke2_api_url "${RKE2_API_URL}"
ctx instance runtime-properties capabilities.rke2_node_status "${RKE2_NODE_STATUS}"
ctx instance runtime-properties capabilities.rke2_join_token "${RKE2_JOIN_TOKEN}"
ctx instance runtime-properties capabilities.rke2_kubeconfig "${RKE2_KUBECONFIG}"
ctx instance runtime-properties capabilities.mgmt_ip "${mgmt_ip}"
