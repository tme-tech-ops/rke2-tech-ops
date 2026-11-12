#!/bin/sh
# create for env_precheck, cp_env_precheck and ag_env_precheck (multi-node):
# puts the RKE2 installer in the home directory of the VM.
#
# Airgapped mode downloads and extracts the offline package every time, so a
# new package with the same name replaces the old one. The package carries its
# own rke2_installer.sh: the one that built it. Otherwise it downloads
# SCRIPT_URL. A GitHub release asset is checked against the SHA256SUMS of the
# same release, and a file that doesn't match isn't kept.
set -u
# The fabric plugin leaves the settings in an env file on the VM. It holds a password.
rm -f "$(dirname "$0")/env-$(basename "$0")"

log() { ctx logger info "$1"; }
fail() { ctx logger error "$1"; exit 1; }

offline_mode=$(printf '%s' "${OFFLINE_MODE:-false}" | tr '[:upper:]' '[:lower:]')

if [ "$offline_mode" = "true" ]; then
    log "Offline mode detected."
    if [ -z "${OFFLINE_BINARY_URL:-}" ] || [ -z "${OFFLINE_BINARY_USER:-}" ] || [ -z "${OFFLINE_BINARY_PASSWORD:-}" ]; then
        fail "OFFLINE_BINARY_URL, OFFLINE_BINARY_USER, or OFFLINE_BINARY_PASSWORD is missing."
    fi
    archive="$HOME/$(basename "$OFFLINE_BINARY_URL")"
    log "Downloading offline binary..."
    curl -skfLu "${OFFLINE_BINARY_USER}:${OFFLINE_BINARY_PASSWORD}" "$OFFLINE_BINARY_URL" -o "$archive" \
        || fail "Failed to download offline binary."
    log "Extracting offline binary..."
    tar -xzf "$archive" -C "$HOME" || fail "Failed to extract offline binary."
    [ -x "$HOME/rke2_installer.sh" ] || fail "The offline binary has no rke2_installer.sh."
    log "Offline binary downloaded and extracted. It runs the rke2_installer.sh it carries ($(sed -n 's/^SCRIPT_VERSION=//p' "$HOME/rke2_installer.sh" | tr -d '"' | head -n 1))."
    exit 0
fi

log "Online mode detected."
[ -n "${SCRIPT_URL:-}" ] || fail "SCRIPT_URL is missing."

script="$HOME/$(basename "$SCRIPT_URL")"
download="${script}.download"
rm -f "$download"
curl -sfL --retry 3 "$SCRIPT_URL" -o "$download" || fail "Failed to download ${SCRIPT_URL}."

case "$SCRIPT_URL" in
    https://github.com/*/releases/download/*/rke2_installer.sh)
        sums_url="${SCRIPT_URL%/*}/SHA256SUMS"
        if ! sums=$(curl -sfL --retry 3 "$sums_url"); then
            rm -f "$download"
            fail "Failed to download ${sums_url}."
        fi
        expected=$(printf '%s\n' "$sums" | awk '$2 == "rke2_installer.sh" || $2 == "*rke2_installer.sh" { print $1; exit }')
        if [ -z "$expected" ]; then
            rm -f "$download"
            fail "${sums_url} has no entry for rke2_installer.sh."
        fi
        actual=$(sha256sum "$download" | awk '{ print $1 }')
        if [ "$actual" != "$expected" ]; then
            rm -f "$download"
            fail "rke2_installer.sh doesn't match ${sums_url} (expected ${expected}, got ${actual})."
        fi
        log "rke2_installer.sh matches the release's SHA256SUMS (${actual})."
        ;;
    *)
        log "${SCRIPT_URL} isn't a GitHub release asset: no checksum to check."
        ;;
esac

if ! { mv -f "$download" "$script" && chmod +x "$script"; }; then
    fail "Failed to put the installer at ${script}."
fi
log "Install script downloaded and made executable: ${SCRIPT_URL}"
