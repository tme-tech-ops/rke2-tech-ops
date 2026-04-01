#!/bin/bash

if [[ ${OFFLINE_MODE,,} == "true" ]]; then
    ctx logger info "Offline mode detected."
    if [[ -z $OFFLINE_BINARY_URL || -z $OFFLINE_BINARY_USER || -z $OFFLINE_BINARY_PASSWORD ]]; then
        ctx logger info "OFFLINE_BINARY_URL, OFFLINE_BINARY_USER, or OFFLINE_BINARY_PASSWORD is missing."
        exit 1
    else
        ctx logger info "Downloading offline binary..."
        ctx logger info "curl -skfLu "$OFFLINE_BINARY_USER:$OFFLINE_BINARY_PASSWORD" $OFFLINE_BINARY_URL -o ~/$(basename $OFFLINE_BINARY_URL)"
        if [[ -f ~/$(basename $OFFLINE_BINARY_URL) ]]; then
            ctx logger info "Offline binary already exists. Skipping download."
        else
            curl -skfLu "${OFFLINE_BINARY_USER}:${OFFLINE_BINARY_PASSWORD}" "${OFFLINE_BINARY_URL}" -o ~/$(basename $OFFLINE_BINARY_URL)
            if [[ $? -ne 0 ]]; then
                ctx logger info "Failed to download offline binary."
                exit 1
            fi
        fi
        ctx logger info "Extracting offline binary..."
        tar -xzf ~/$(basename $OFFLINE_BINARY_URL) -C ~/
        if [[ $? -ne 0 ]]; then
            ctx logger info "Failed to extract offline binary."
            exit 1
        fi
        ctx logger info "Offline binary downloaded and extracted."
    fi
else
    ctx logger info "Online mode detected."
    if [[ -z $SCRIPT_URL ]]; then
        ctx logger info "SCRIPT_URL is missing."
        exit 1
    fi
    curl -skfL $SCRIPT_URL -o ~/$(basename $SCRIPT_URL)
    if [[ $? -ne 0 ]]; then
        ctx logger info "Failed to download script."
        exit 1
    fi
    chmod +x ~/$(basename $SCRIPT_URL)
    ctx logger info "Install script downloaded and made executable."
fi

# Install command parsing
ctx logger info "Assembling install command for run_arg: ${RUN_ARG}"
INSTALL_CMD="${RUN_ARG}"

# Handle join mode: append join_mode, join_server, join_token as positional args
if [[ "$RUN_ARG" == "join" ]]; then
    if [[ -z "$JOIN_MODE" || "$JOIN_MODE" == "None" ]]; then
        ctx logger info "JOIN_MODE is required for join command."
        exit 1
    fi
    if [[ -z "$JOIN_SERVER" || "$JOIN_SERVER" == "None" ]]; then
        ctx logger info "JOIN_SERVER is required for join command."
        exit 1
    fi
    if [[ -z "$JOIN_TOKEN" || "$JOIN_TOKEN" == "None" ]]; then
        ctx logger info "JOIN_TOKEN is required for join command."
        exit 1
    fi
    INSTALL_CMD="${INSTALL_CMD} ${JOIN_MODE} ${JOIN_SERVER} ${JOIN_TOKEN}"
fi

# Append optional -tls-san flag
if [[ -n "$TLS_SAN" && "$TLS_SAN" != "None" ]]; then
    INSTALL_CMD="${INSTALL_CMD} -tls-san ${TLS_SAN}"
fi

# Append optional -registry flag
if [[ -n "$REG_URL" && "$REG_URL" != "None" ]]; then
    INSTALL_CMD="${INSTALL_CMD} -registry ${REG_URL} ${REG_USER} ${REG_PASS}"
fi

ctx logger info "parsed install command: ${INSTALL_CMD}"
ctx instance runtime-properties capabilities.install_cmd "$INSTALL_CMD"
