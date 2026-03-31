#!/bin/sh
set -eu

cleanup() {
    rc=$?
    ctx logger info "ag_env_postcheck.sh exiting with code ${rc}"
    exit $rc
}
trap cleanup EXIT

RKE2_RUNNING="false"
RKE2_NODE_STATUS="N/A"

ctx logger info "AG join post-check started."

# Verify rke2-agent service is active on joined agent node
if systemctl is-active --quiet rke2-agent 2>/dev/null; then
    ctx logger info "RKE2 agent service is running on joined AG node."
    RKE2_RUNNING="true"
    RKE2_NODE_STATUS="Agent running"
else
    ctx logger info "RKE2 agent service is NOT running on joined AG node."
fi

ctx logger info "AG join post-check completed."
ctx instance runtime-properties capabilities.rke2_running "${RKE2_RUNNING}"
ctx instance runtime-properties capabilities.rke2_node_status "${RKE2_NODE_STATUS}"
