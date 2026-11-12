#!/bin/sh
# create for the RKE2 install nodes (multi-node): runs ~/rke2_installer.sh for
# this VM's role, with the cluster's settings in the environment.
#
#   ROLE=cp1    install_app: install the first control plane (and push the
#               RKE2 images to the registry first, with Push Images).
#   ROLE=cp     install_cp: join CP2-3 as servers.
#   ROLE=agent  install_ag: join agents 1-6.
#
# The installer gets each argument whole: the join token and the registry
# password are never part of a command string, so they aren't logged, stored
# in a runtime property, split at spaces or expanded.
#
# A reinstall during an update ("Run automatic reinstall" or a reinstall list)
# and Heal run this again. The installer converges: with nothing changed it
# changes nothing.
set -u
# The fabric plugin leaves the settings in an env file on the VM. It holds passwords.
rm -f "$(dirname "$0")/env-$(basename "$0")"

log() { ctx logger info "$1"; }
fail() { ctx logger error "$1"; exit 1; }
# An optional input cleared in the form can arrive as None.
value() { [ "${1:-}" = "None" ] && return 0; printf '%s' "${1:-}"; }

role="${ROLE:-}"
tls_san="$(value "${TLS_SAN:-}")"
reg_url="$(value "${REG_URL:-}")"
reg_user="$(value "${REG_USER:-}")"
reg_pass="$(value "${REG_PASS:-}")"
push_images=$(printf '%s' "$(value "${PUSH_IMAGES:-false}")" | tr '[:upper:]' '[:lower:]')
join_server="$(value "${JOIN_SERVER:-}")"
join_token="$(value "${JOIN_TOKEN:-}")"
# They reach the installer as arguments only, so its environment holds no copy.
unset ROLE TLS_SAN REG_URL REG_USER REG_PASS PUSH_IMAGES JOIN_SERVER JOIN_TOKEN

case "$role" in
    cp1)
        set -- install
        shown=install
        if [ -n "$reg_url" ] && [ "$push_images" = "true" ]; then
            set -- install push
            shown="install push"
        fi
        ;;
    cp|agent)
        # The token is CP1's node-token, which starts with K10. env_postcheck
        # publishes N/A when it can't read it; joining with that fails late.
        case "$join_token" in
            K10*) ;;
            *) fail "No usable join token from the first control plane (a node-token starts with K10): its env_postcheck didn't publish one." ;;
        esac
        [ -n "$join_server" ] || fail "No join server: the first control plane's env_postcheck didn't publish its address."
        # Prefer the TLS SAN over CP1's address: it stays valid if CP1's address changes.
        if [ -n "$tls_san" ]; then
            log "TLS SAN is set: joining through ${tls_san} instead of ${join_server}."
            join_server="$tls_san"
        fi
        if [ "$role" = cp ]; then
            set -- join server "$join_server" "$join_token"
            shown="join server ${join_server} ****"
        else
            set -- join agent "$join_server" "$join_token"
            shown="join agent ${join_server} ****"
            # Only servers read these. Left out, the agent's installer doesn't warn
            # that it ignores them.
            unset CLUSTER_CIDR SERVICE_CIDR INSTALL_SERVICELB INSTALL_LOCAL_PATH_PROVISIONER \
                INSTALL_DNS_UTILITY CONTROL_PLANE_TAINT PVC_DATA
        fi
        ;;
    *) fail "Unknown role '${role}'." ;;
esac

# Servers take the TLS SAN for their API certificate; agents don't use it.
if [ -n "$tls_san" ] && [ "$role" != agent ]; then
    set -- "$@" -tls-san "$tls_san"
    shown="${shown} -tls-san ${tls_san}"
fi

if [ -n "$reg_url" ]; then
    [ -n "$reg_user" ] && [ -n "$reg_pass" ] \
        || fail "Registry URL is set, but the Registry Authentication Secret gave no username or password."
    set -- "$@" -registry "$reg_url" "$reg_user" "$reg_pass"
    shown="${shown} -registry ${reg_url} ${reg_user} ****"
fi

cd ~ || fail "No home directory."
[ -x ./rke2_installer.sh ] || fail "~/rke2_installer.sh is missing: the precheck didn't put it there."
log "Running: rke2_installer.sh ${shown} (installer $(sed -n 's/^SCRIPT_VERSION=//p' ./rke2_installer.sh | tr -d '"' | head -n 1))"
sudo -E ./rke2_installer.sh "$@"
rc=$?
# Exit 1 isn't retried (non_recoverable_error_exit_codes): a retry would re-run
# the installer for a long time.
[ "$rc" -eq 0 ] || fail "rke2_installer.sh ${shown} failed with exit code ${rc}."
log "rke2_installer.sh ${shown} completed."
