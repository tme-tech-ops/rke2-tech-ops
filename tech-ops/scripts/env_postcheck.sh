#!/bin/sh
# create for env_postcheck (standalone): checks the result of the Install Task
# and publishes it as capabilities, then uploads the offline package if asked.
#
# After a task that installs RKE2 (install, install push, join) the rke2 service
# must be active, or the check fails. A node that isn't Ready is reported, not
# failed: with CNI none it stays NotReady until a CNI is installed.
#
# It runs as the VM user, so ~ is the home directory where the installer ran;
# what needs root runs with sudo.
set -u
# The fabric plugin leaves the settings in an env file on the VM. It holds a password.
rm -f "$(dirname "$0")/env-$(basename "$0")"

log() { ctx logger info "$1"; }
fail() { ctx logger error "$1"; exit 1; }
value() { [ "${1:-}" = "None" ] && return 0; printf '%s' "${1:-}"; }

OFFLINE_PACKAGE_NAME="rke2-save.tar.gz"
OFFLINE_PACKAGE_UPLOADED="false"
OFFLINE_PACKAGE_URL="N/A"
RKE2_RUNNING="false"
RKE2_NODE_STATUS="N/A"
RKE2_API_URL="N/A"
RKE2_JOIN_TOKEN="N/A"
RKE2_KUBECONFIG="N/A"

task="$(value "${RUN_ARG:-install}")"
[ -n "$task" ] || task=install
rke2_data="$(value "${RKE2_DATA:-default}")"
case "$rke2_data" in ""|default) rke2_data=/var/lib/rancher/rke2 ;; esac
mgmt_ip=$(hostname -I | awk '{print $1}')

log "Post install check started."

if systemctl is-active --quiet rke2-server 2>/dev/null; then
    log "RKE2 server service is running."
    RKE2_RUNNING="true"
    RKE2_API_URL="https://$mgmt_ip:6443"
    RKE2_KUBECONFIG="/etc/rancher/rke2/rke2.yaml"
    if sudo "$rke2_data/bin/kubectl" --kubeconfig /etc/rancher/rke2/rke2.yaml \
            wait --for=condition=Ready nodes --all --timeout=120s >/dev/null 2>&1; then
        RKE2_NODE_STATUS="Ready"
    else
        RKE2_NODE_STATUS="NotReady"
    fi
    log "RKE2 cluster status: ${RKE2_NODE_STATUS}"
    if token=$(sudo cat "$rke2_data/server/node-token" 2>/dev/null) && [ -n "$token" ]; then
        RKE2_JOIN_TOKEN="$token"
        log "Captured the join token from ${rke2_data}/server/node-token."
    else
        log "No join token at ${rke2_data}/server/node-token."
    fi
elif systemctl is-active --quiet rke2-agent 2>/dev/null; then
    log "RKE2 agent service is running."
    RKE2_RUNNING="true"
    RKE2_API_URL="N/A (agent node)"
    RKE2_NODE_STATUS="Agent node - check server for status"
    RKE2_KUBECONFIG="N/A (agent node)"
else
    case "$task" in
        install|"install push"|join)
            fail "RKE2 isn't running after Install Task '${task}': neither rke2-server nor rke2-agent is active."
            ;;
        *)
            log "RKE2 service is not running (Install Task '${task}')."
            ;;
    esac
fi

# Offline package upload logic
if [ -f ~/"${OFFLINE_PACKAGE_NAME}" ]; then
    log "Offline package found: ${OFFLINE_PACKAGE_NAME}"
    upload=$(printf '%s' "${UPLOAD_OFFLINE_PACKAGE:-false}" | tr '[:upper:]' '[:lower:]')
    log "Upload package: ${upload}"
    if [ "$upload" = "true" ]; then
        if [ -z "$(value "${UPLOAD_BASE_URL:-}")" ] || [ -z "$(value "${UPLOAD_OFFLINE_PACKAGE_USER:-}")" ] \
                || [ -z "$(value "${UPLOAD_OFFLINE_PACKAGE_PASSWORD:-}")" ]; then
            fail "UPLOAD_BASE_URL, UPLOAD_OFFLINE_PACKAGE_USER, or UPLOAD_OFFLINE_PACKAGE_PASSWORD is missing."
        fi
        log "Uploading offline package..."
        new_offline_package_name="$(date +%Y%m%d%H%M)-${OFFLINE_PACKAGE_NAME}"
        mv ~/"${OFFLINE_PACKAGE_NAME}" ~/"${new_offline_package_name}" || fail "Failed to rename the offline package."
        OFFLINE_PACKAGE_URL="${UPLOAD_BASE_URL}${new_offline_package_name}"
        curl -sfku "${UPLOAD_OFFLINE_PACKAGE_USER}:${UPLOAD_OFFLINE_PACKAGE_PASSWORD}" \
            -X POST "$OFFLINE_PACKAGE_URL" \
            -F "file=@$HOME/${new_offline_package_name}" >/dev/null \
            || fail "Failed to upload offline package."
        OFFLINE_PACKAGE_UPLOADED="true"
        OFFLINE_PACKAGE_NAME="$new_offline_package_name"
        log "Offline package uploaded to $OFFLINE_PACKAGE_URL."
    fi
else
    log "Offline package (${OFFLINE_PACKAGE_NAME}) not found. Skipping upload."
    OFFLINE_PACKAGE_NAME="N/A"
fi

log "Post install check completed."
ctx instance runtime-properties capabilities.rke2_running "$RKE2_RUNNING"
ctx instance runtime-properties capabilities.rke2_api_url "$RKE2_API_URL"
ctx instance runtime-properties capabilities.rke2_node_status "$RKE2_NODE_STATUS"
ctx instance runtime-properties capabilities.rke2_join_token "$RKE2_JOIN_TOKEN"
ctx instance runtime-properties capabilities.rke2_kubeconfig "$RKE2_KUBECONFIG"
ctx instance runtime-properties capabilities.offline_package_name "$OFFLINE_PACKAGE_NAME"
ctx instance runtime-properties capabilities.offline_package_uploaded "$OFFLINE_PACKAGE_UPLOADED"
ctx instance runtime-properties capabilities.offline_package_url "$OFFLINE_PACKAGE_URL"
