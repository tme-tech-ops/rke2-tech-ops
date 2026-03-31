#!/bin/sh
set -eu

cleanup() {
    rc=$?
    ctx logger info "cp_env_postcheck.sh exiting with code ${rc}"
    exit $rc
}
trap cleanup EXIT

RKE2_RUNNING="false"
RKE2_NODE_STATUS="N/A"

ctx logger info "CP join post-check started."

# Verify rke2-server service is active on joined control-plane node
if systemctl is-active --quiet rke2-server 2>/dev/null; then
    ctx logger info "RKE2 server service is running on joined CP node."
    RKE2_RUNNING="true"

    export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
    export PATH="${PATH}:/var/lib/rancher/rke2/bin"
    if command -v kubectl >/dev/null 2>&1; then
        node_name=$(hostname)
        if kubectl wait --for=condition=Ready "node/${node_name}" --timeout=120s >/dev/null 2>&1; then
            RKE2_NODE_STATUS="Ready"
            ctx logger info "Joined CP node status: Ready"
        else
            RKE2_NODE_STATUS="NotReady"
            ctx logger info "Joined CP node status: NotReady"
        fi
    fi
else
    ctx logger info "RKE2 server service is NOT running on joined CP node."
fi

ctx logger info "CP join post-check completed."
ctx instance runtime-properties capabilities.rke2_running "${RKE2_RUNNING}"
ctx instance runtime-properties capabilities.rke2_node_status "${RKE2_NODE_STATUS}"
