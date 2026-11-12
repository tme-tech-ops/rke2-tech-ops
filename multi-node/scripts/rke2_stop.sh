#!/bin/sh
set -u

# stop for the RKE2 install nodes (install_app, install_cp, install_ag).
#
# RKE2 and its data are removed only when the deployment is uninstalled or a
# node is scaled away. The cluster's data paths go to the installer, so custom
# paths are removed too. Other workflows run stop too: a reinstall during an
# update ("Run automatic reinstall" or a reinstall list) and Heal. In those the
# node stays in the cluster with its data, and the create that follows re-runs
# the installer, which finds RKE2 installed and leaves it as it is.

# The fabric plugin leaves the settings in an env file on the VM.
rm -f "$(dirname "$0")/env-$(basename "$0")"

# Rancher's rke2-uninstall.sh and rke2-killall.sh find RKE2's processes under
# RKE2_DATA_DIR (default /var/lib/rancher/rke2), and installer v1.3.1 doesn't
# pass them the data path. With a custom path the pods would keep running from
# a deleted directory. sudo -E carries this through the installer to them.
case "${RKE2_DATA:-default}" in
    ""|default|None) ;;
    *) RKE2_DATA_DIR="$RKE2_DATA"; export RKE2_DATA_DIR ;;
esac

workflow="$(ctx workflow-id 2>/dev/null || echo unknown)"

case "${workflow}" in
    uninstall|scale)
        if [ -x ~/rke2_installer.sh ]; then
            ctx logger info "Uninstalling RKE2 (${workflow} workflow)."
            cd ~ && sudo -E ./rke2_installer.sh uninstall
        else
            ctx logger info "rke2_installer.sh not found in the home directory: nothing to uninstall."
        fi
        ;;
    *)
        ctx logger info "Keeping RKE2 and its data (${workflow} workflow): only uninstalling the deployment removes them."
        ;;
esac
