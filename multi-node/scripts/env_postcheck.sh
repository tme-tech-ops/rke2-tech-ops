#!/bin/sh
set -eu

cleanup() {
    rc=$?
    ctx logger info "env_postcheck.sh exiting with code ${rc}"
    exit $rc
}
trap cleanup EXIT
# The fabric plugin leaves the settings in an env file on the VM.
rm -f "$(dirname "$0")/env-$(basename "$0")"

# CP1 must run rke2-server, Ready or not (with CNI none it stays NotReady), and
# have a join token: CP2-3 and the agents join with it.
rke2_data="${RKE2_DATA:-default}"
case "$rke2_data" in ""|default|None) rke2_data=/var/lib/rancher/rke2 ;; esac

RKE2_RUNNING="false"
RKE2_NODE_STATUS="N/A"
RKE2_API_URL="N/A"
RKE2_JOIN_TOKEN="N/A"
RKE2_KUBECONFIG="N/A"
RKE2_CA_CERT="N/A"
RKE2_CA_CERT_B64="N/A"
SERVICE_ACCOUNT="N/A"
BEARER_TOKEN="N/A"

mgmt_ip=$(hostname -I | awk '{print $1}')

ctx logger info "Post install check started."

# Primary health check: verify rke2-server service is active (CP1 is always a server)
if systemctl is-active --quiet rke2-server 2>/dev/null; then
    ctx logger info "RKE2 server service is running."
    RKE2_RUNNING="true"
    RKE2_API_URL="https://${mgmt_ip}:6443"

    # Attempt to get node status
    export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
    export PATH="${PATH}:${rke2_data}/bin"
    if command -v kubectl >/dev/null 2>&1; then
        if kubectl wait --for=condition=Ready nodes --all --timeout=120s >/dev/null 2>&1; then
            RKE2_NODE_STATUS="Ready"
            ctx logger info "RKE2 cluster status: Ready"
        else
            RKE2_NODE_STATUS="NotReady"
            ctx logger info "RKE2 cluster status: NotReady"
        fi
    fi

    # The join token, from the cluster's data path
    if [ -s "${rke2_data}/server/node-token" ]; then
        RKE2_JOIN_TOKEN=$(cat "${rke2_data}/server/node-token")
        ctx logger info "Captured the join token from ${rke2_data}/server/node-token."
    else
        ctx logger error "No join token at ${rke2_data}/server/node-token: CP2-3 and the agents can't join."
        exit 1
    fi

    RKE2_KUBECONFIG="/etc/rancher/rke2/rke2.yaml"

    # Get CA certificate - both base64 and decoded PEM
    RKE2_CA_CERT_B64=$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')
    RKE2_CA_CERT=$(printf '%s' "$RKE2_CA_CERT_B64" | base64 -d)
    ctx logger info "Captured RKE2 CA certificate."

    # Create service account for DAP integration
    SERVICE_ACCOUNT="${SA_NAMESPACE}-sa"
    BEARER_TOKEN_NAME="${SA_NAMESPACE}-token"
    ROLE_BIND_NAME="${SA_NAMESPACE}-binding"

    kubectl create namespace "$SA_NAMESPACE" 2>/dev/null || ctx logger info "Namespace $SA_NAMESPACE already exists."
    kubectl create serviceaccount "$SERVICE_ACCOUNT" -n "$SA_NAMESPACE" 2>/dev/null || ctx logger info "SA already exists."
    kubectl create clusterrolebinding "$ROLE_BIND_NAME" \
        --clusterrole=cluster-admin \
        --serviceaccount="$SA_NAMESPACE:$SERVICE_ACCOUNT" 2>/dev/null || ctx logger info "CRB already exists."

    kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: $BEARER_TOKEN_NAME
  namespace: $SA_NAMESPACE
  annotations:
    kubernetes.io/service-account.name: $SERVICE_ACCOUNT
type: kubernetes.io/service-account-token
EOF

    # Wait for token controller to populate the secret
    attempts=0
    while [ $attempts -lt 6 ]; do
        BEARER_TOKEN=$(kubectl get secret "$BEARER_TOKEN_NAME" -n "$SA_NAMESPACE" \
            -o jsonpath='{.data.token}' 2>/dev/null | base64 -d 2>/dev/null) || true
        if [ -n "$BEARER_TOKEN" ] && [ "$BEARER_TOKEN" != "N/A" ]; then
            break
        fi
        attempts=$((attempts + 1))
        sleep 5
    done
    ctx logger info "SA setup complete: $SERVICE_ACCOUNT in $SA_NAMESPACE"
else
    ctx logger error "RKE2 server service is not running on CP1."
    exit 1
fi

ctx logger info "Post install check completed."
ctx instance runtime-properties capabilities.rke2_running "${RKE2_RUNNING}"
ctx instance runtime-properties capabilities.rke2_api_url "${RKE2_API_URL}"
ctx instance runtime-properties capabilities.rke2_node_status "${RKE2_NODE_STATUS}"
ctx instance runtime-properties capabilities.rke2_join_token "${RKE2_JOIN_TOKEN}"
ctx instance runtime-properties capabilities.rke2_kubeconfig "${RKE2_KUBECONFIG}"
ctx instance runtime-properties capabilities.mgmt_ip "${mgmt_ip}"
ctx instance runtime-properties capabilities.rke2_ca_cert "${RKE2_CA_CERT}"
ctx instance runtime-properties capabilities.rke2_ca_cert_b64 "${RKE2_CA_CERT_B64}"
ctx instance runtime-properties capabilities.service_account "${SERVICE_ACCOUNT}"
ctx instance runtime-properties capabilities.bearer_token "${BEARER_TOKEN}"
