#!/bin/sh
set -eu

cleanup() {
    rc=$?
    ctx logger info "ag_env_precheck.sh exiting with code ${rc}"
    exit $rc
}
trap cleanup EXIT

# AG join precheck: download installer and assemble "join agent" command

if [ "$(echo "${OFFLINE_MODE}" | tr '[:upper:]' '[:lower:]')" = "true" ]; then
    ctx logger info "Offline mode detected."
    if [ -z "${OFFLINE_BINARY_URL:-}" ] || [ -z "${OFFLINE_BINARY_USER:-}" ] || [ -z "${OFFLINE_BINARY_PASSWORD:-}" ]; then
        ctx logger info "OFFLINE_BINARY_URL, OFFLINE_BINARY_USER, or OFFLINE_BINARY_PASSWORD is missing."
        exit 1
    fi
    offline_file="$(basename "${OFFLINE_BINARY_URL}")"
    if [ -f ~/"${offline_file}" ]; then
        ctx logger info "Offline binary already exists. Skipping download."
    else
        ctx logger info "Downloading offline binary..."
        curl -skfLu "${OFFLINE_BINARY_USER}:${OFFLINE_BINARY_PASSWORD}" "${OFFLINE_BINARY_URL}" -o ~/"${offline_file}"
        if [ $? -ne 0 ]; then
            ctx logger info "Failed to download offline binary."
            exit 1
        fi
    fi
    ctx logger info "Extracting offline binary..."
    tar -xzf ~/"${offline_file}" -C ~/
    if [ $? -ne 0 ]; then
        ctx logger info "Failed to extract offline binary."
        exit 1
    fi
    ctx logger info "Offline binary downloaded and extracted."
else
    ctx logger info "Online mode detected."
    if [ -z "${SCRIPT_URL:-}" ]; then
        ctx logger info "SCRIPT_URL is missing."
        exit 1
    fi
    script_file="$(basename "${SCRIPT_URL}")"
    curl -skfL "${SCRIPT_URL}" -o ~/"${script_file}"
    if [ $? -ne 0 ]; then
        ctx logger info "Failed to download script."
        exit 1
    fi
    chmod +x ~/"${script_file}"
    ctx logger info "Install script downloaded and made executable."
fi

# Validate join parameters
if [ -z "${JOIN_SERVER:-}" ] || [ "${JOIN_SERVER}" = "None" ]; then
    ctx logger info "JOIN_SERVER is required for join agent command."
    exit 1
fi
if [ -z "${JOIN_TOKEN:-}" ] || [ "${JOIN_TOKEN}" = "None" ]; then
    ctx logger info "JOIN_TOKEN is required for join agent command."
    exit 1
fi

# Assemble join agent command (no -tls-san for agents)
INSTALL_CMD="join agent ${JOIN_SERVER} ${JOIN_TOKEN}"

# Append optional -registry flag
if [ -n "${REG_URL:-}" ] && [ "${REG_URL}" != "None" ]; then
    INSTALL_CMD="${INSTALL_CMD} -registry ${REG_URL} ${REG_USER} ${REG_PASS}"
fi

ctx logger info "Parsed install command: ${INSTALL_CMD}"
ctx instance runtime-properties capabilities.install_cmd "${INSTALL_CMD}"
