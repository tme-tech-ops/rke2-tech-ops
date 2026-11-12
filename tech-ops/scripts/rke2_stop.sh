#!/bin/sh
set -u

# stop for install_app (standalone).
#
# RKE2 and its data are removed only when this deployment is uninstalled, and
# only if its Install Task installed RKE2 (install, install push, join). The
# other tasks (install velero, install monitoring, save, push, uninstall) work
# on a cluster another deployment installed, so uninstalling them leaves RKE2,
# and what the task added, in place. The deployment's data paths go to the
# installer, so custom paths are removed too.
#
# Other workflows run stop too: a reinstall during an update ("Run automatic
# reinstall" or a reinstall list) and Heal. In those RKE2 stays as it is.

# The fabric plugin leaves the settings in an env file on the VM.
rm -f "$(dirname "$0")/env-$(basename "$0")"

# Rancher's rke2-uninstall.sh and rke2-killall.sh find RKE2's processes under
# RKE2_DATA_DIR (default /var/lib/rancher/rke2), and installer v1.3.1 doesn't
# pass them the data path. With a custom path the pods would keep running from
# a deleted directory, holding the API port, and the next install on the VM
# would fail. sudo -E carries this through the installer to them.
case "${RKE2_DATA:-default}" in
    ""|default|None) ;;
    *) RKE2_DATA_DIR="$RKE2_DATA"; export RKE2_DATA_DIR ;;
esac

workflow="$(ctx workflow-id 2>/dev/null || echo unknown)"

case "${workflow}" in
    uninstall)
        case "${RUN_ARG:-install}" in
            install|"install push"|join)
                if [ -x ~/rke2_installer.sh ]; then
                    ctx logger info "Uninstalling RKE2 (Install Task '${RUN_ARG:-install}')."
                    cd ~ && sudo -E ./rke2_installer.sh uninstall
                else
                    ctx logger info "rke2_installer.sh not found in the home directory: nothing to uninstall."
                fi
                ;;
            *)
                ctx logger info "Install Task '${RUN_ARG}' didn't install RKE2: leaving RKE2 in place."
                ;;
        esac
        ;;
    *)
        ctx logger info "Keeping RKE2 and its data (${workflow} workflow): only uninstalling the deployment removes them."
        ;;
esac
