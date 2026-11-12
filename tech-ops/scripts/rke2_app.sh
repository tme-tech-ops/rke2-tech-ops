#!/bin/sh
# create for install_app (standalone): runs ~/rke2_installer.sh for the Install
# Task, with the deployment's settings in the environment.
#
# The installer gets each argument whole: the join token and the registry
# password are never part of a command string, so they aren't logged, stored
# in a runtime property, split at spaces or expanded.
#
# A reinstall during an update ("Run automatic reinstall" or a reinstall list)
# and Heal run this again. The installer converges: with nothing changed it
# changes nothing. The uninstall task runs only in the install workflow, so a
# reinstall or Heal doesn't uninstall RKE2 again.
set -u
# The fabric plugin leaves the settings in an env file on the VM. It holds passwords.
rm -f "$(dirname "$0")/env-$(basename "$0")"

log() { ctx logger info "$1"; }
fail() { ctx logger error "$1"; exit 1; }
# An optional input cleared in the form can arrive as None.
value() { [ "${1:-}" = "None" ] && return 0; printf '%s' "${1:-}"; }

workflow="$(ctx workflow-id 2>/dev/null || echo unknown)"
task="$(value "${RUN_ARG:-install}")"
[ -n "$task" ] || task=install
tls_san="$(value "${TLS_SAN:-}")"
reg_url="$(value "${REG_URL:-}")"
reg_user="$(value "${REG_USER:-}")"
reg_pass="$(value "${REG_PASS:-}")"
join_mode="$(value "${JOIN_MODE:-}")"
join_server="$(value "${JOIN_SERVER:-}")"
join_token="$(value "${JOIN_TOKEN:-}")"
# They reach the installer as arguments only, so its environment holds no copy.
unset RUN_ARG TLS_SAN REG_URL REG_USER REG_PASS JOIN_MODE JOIN_SERVER JOIN_TOKEN

case "$task" in
    install) set -- install ;;
    "install push") set -- install push ;;
    "install velero") set -- install velero ;;
    "install monitoring") set -- install monitoring ;;
    save) set -- save ;;
    push) set -- push ;;
    uninstall)
        if [ "$workflow" != "install" ]; then
            log "Install Task 'uninstall' runs only when the deployment is installed: nothing to do (${workflow} workflow)."
            exit 0
        fi
        set -- uninstall
        ;;
    join)
        case "$join_mode" in
            server|agent) ;;
            *) fail "Install Task 'join' needs Join Mode server or agent." ;;
        esac
        [ -n "$join_server" ] || fail "Install Task 'join' needs Join Server."
        [ -n "$join_token" ] || fail "Install Task 'join' needs Join Token."
        set -- join "$join_mode" "$join_server" "$join_token"
        ;;
    *) fail "Unknown Install Task '${task}'." ;;
esac
shown="$task"
[ "$task" = join ] && shown="join ${join_mode} ${join_server} ****"

# -tls-san: the installer takes it with install and join server only.
if [ -n "$tls_san" ]; then
    case "$task" in
        install|"install push") set -- "$@" -tls-san "$tls_san"; shown="${shown} -tls-san ${tls_san}" ;;
        join)
            if [ "$join_mode" = server ]; then
                set -- "$@" -tls-san "$tls_san"; shown="${shown} -tls-san ${tls_san}"
            else
                log "An agent doesn't use TLS SAN: it is ignored."
            fi
            ;;
        *) log "Install Task '${task}' doesn't use TLS SAN: it is ignored." ;;
    esac
fi

# -registry: install and join pull through it, push and install push push to
# it. The installer refuses it with uninstall and save, and install velero and
# install monitoring don't read it.
case "$task" in
    install|"install push"|push|join)
        if [ -n "$reg_url" ]; then
            [ -n "$reg_user" ] && [ -n "$reg_pass" ] \
                || fail "Registry URL is set, but the Registry Authentication Secret gave no username or password."
            set -- "$@" -registry "$reg_url" "$reg_user" "$reg_pass"
            shown="${shown} -registry ${reg_url} ${reg_user} ****"
        fi
        ;;
    *)
        [ -n "$reg_url" ] && log "Install Task '${task}' doesn't use the registry: Registry URL is ignored."
        ;;
esac
case "$task" in
    push|"install push")
        [ -n "$reg_url" ] || fail "Install Task '${task}' needs Registry URL and the Registry Authentication Secret."
        ;;
esac

cd ~ || fail "No home directory."
[ -x ./rke2_installer.sh ] || fail "~/rke2_installer.sh is missing: env_precheck didn't put it there."
log "Running: rke2_installer.sh ${shown} (installer $(sed -n 's/^SCRIPT_VERSION=//p' ./rke2_installer.sh | tr -d '"' | head -n 1))"
sudo -E ./rke2_installer.sh "$@"
rc=$?
# Exit 1 isn't retried (non_recoverable_error_exit_codes): a retry would re-run
# the installer for a long time.
[ "$rc" -eq 0 ] || fail "rke2_installer.sh ${shown} failed with exit code ${rc}."
log "rke2_installer.sh ${shown} completed."
