#!/bin/bash

OFFLINE_PACKAGE_NAME="rke2-save.tar.gz"
OFFLINE_PACKAGE_UPLOADED="false"
OFFLINE_PACKAGE_URL="N/A"
RKE2_RUNNING="false"
RKE2_NODE_STATUS="N/A"
RKE2_API_URL="N/A"
RKE2_JOIN_TOKEN="N/A"
RKE2_KUBECONFIG="N/A"

mgmt_ip=$(hostname -I | awk '{print $1}')

ctx logger info "Post install check started."

# Primary health check: verify rke2-server or rke2-agent service is active
if systemctl is-active --quiet rke2-server 2>/dev/null; then
    ctx logger info "RKE2 server service is running."
    RKE2_RUNNING="true"
    RKE2_API_URL="https://$mgmt_ip:6443"

    # Attempt to get node status
    export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
    export PATH=$PATH:/var/lib/rancher/rke2/bin
    if command -v kubectl &>/dev/null; then
        kubectl wait --for=condition=Ready nodes --all --timeout=30s &>/dev/null
        if [[ $? != 0 ]]; then 
            RKE2_NODE_STATUS="NotReady"
            ctx logger info "RKE2 cluster status: NotReady"
        else 
            RKE2_NODE_STATUS="Ready"
            ctx logger info "RKE2 cluster status: Ready"
        fi
    fi

    # Get join token if available
    if [[ -f /var/lib/rancher/rke2/server/node-token ]]; then
        RKE2_JOIN_TOKEN=$(sudo cat /var/lib/rancher/rke2/server/node-token)
        ctx logger info "Captured join token."
    fi

    RKE2_KUBECONFIG="/etc/rancher/rke2/rke2.yaml"

elif systemctl is-active --quiet rke2-agent 2>/dev/null; then
    ctx logger info "RKE2 agent service is running."
    RKE2_RUNNING="true"
    RKE2_API_URL="N/A (agent node)"
    RKE2_NODE_STATUS="Agent node - check server for status"
    RKE2_KUBECONFIG="N/A (agent node)"
else
    ctx logger info "RKE2 service is not running."
    # Check if this was an uninstall, save, or push operation (no service expected)
    if [[ "$RUN_ARG" == "uninstall" || "$RUN_ARG" == "save" || "$RUN_ARG" == "push" ]]; then
        ctx logger info "Operation was '${RUN_ARG}' - RKE2 service not expected to be running."
    fi
fi

# Offline package upload logic
if [[ -f ~/"${OFFLINE_PACKAGE_NAME}" ]]; then
    ctx logger info "Offline package found: ${OFFLINE_PACKAGE_NAME}"
    ctx logger info "Upload package: $UPLOAD_OFFLINE_PACKAGE"
    if [[ ${UPLOAD_OFFLINE_PACKAGE,,} == "true" ]]; then
        ctx logger info "Uploading offline package..."
        new_offline_package_name="$(date +%Y%m%d%H%M)-${OFFLINE_PACKAGE_NAME}"
        mv ~/"${OFFLINE_PACKAGE_NAME}" ~/"${new_offline_package_name}"
        if [[ -z $UPLOAD_BASE_URL || -z $UPLOAD_OFFLINE_PACKAGE_USER || -z $UPLOAD_OFFLINE_PACKAGE_PASSWORD ]]; then
            ctx logger info "UPLOAD_BASE_URL, UPLOAD_OFFLINE_PACKAGE_USER, or UPLOAD_OFFLINE_PACKAGE_PASSWORD is missing."
            exit 1
        else
            OFFLINE_PACKAGE_URL="${UPLOAD_BASE_URL}${new_offline_package_name}"
            curl -ku "${UPLOAD_OFFLINE_PACKAGE_USER}:${UPLOAD_OFFLINE_PACKAGE_PASSWORD}" \
                -X POST "$OFFLINE_PACKAGE_URL" \
                -F "file=@$HOME/${new_offline_package_name}"
            if [[ $? -ne 0 ]]; then
                ctx logger info "Failed to upload offline package."
                exit 1
            fi
        fi
        OFFLINE_PACKAGE_UPLOADED="true"
        OFFLINE_PACKAGE_NAME="$new_offline_package_name"
        ctx logger info "Offline package uploaded to $OFFLINE_PACKAGE_URL."
    fi
else
    ctx logger info "Offline package (${OFFLINE_PACKAGE_NAME}) not found. Skipping upload."
    OFFLINE_PACKAGE_NAME="N/A"
fi

ctx logger info "Post install check completed."
ctx instance runtime-properties capabilities.rke2_running "$RKE2_RUNNING"
ctx instance runtime-properties capabilities.rke2_api_url "$RKE2_API_URL"
ctx instance runtime-properties capabilities.rke2_node_status "$RKE2_NODE_STATUS"
ctx instance runtime-properties capabilities.rke2_join_token "$RKE2_JOIN_TOKEN"
ctx instance runtime-properties capabilities.rke2_kubeconfig "$RKE2_KUBECONFIG"
ctx instance runtime-properties capabilities.offline_package_name "$OFFLINE_PACKAGE_NAME"
ctx instance runtime-properties capabilities.offline_package_uploaded "$OFFLINE_PACKAGE_UPLOADED"
ctx instance runtime-properties capabilities.offline_package_url "$OFFLINE_PACKAGE_URL"
