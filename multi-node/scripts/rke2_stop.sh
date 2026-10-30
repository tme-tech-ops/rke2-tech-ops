#!/bin/sh
set -u

# stop for the RKE2 install nodes (install_app, install_cp, install_ag).
#
# RKE2 and its data are removed only when the deployment is uninstalled or a
# node is scaled away. Other workflows run stop too: a reinstall during an
# update ("Run automatic reinstall" or a reinstall list) and Heal. In those the
# node stays in the cluster with its data, and the create that follows re-runs
# the installer, which finds RKE2 installed and leaves it as it is.

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
