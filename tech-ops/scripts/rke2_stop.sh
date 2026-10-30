#!/bin/sh
set -u

# stop for install_app (standalone).
#
# RKE2 and its data are removed only when this deployment is uninstalled, and
# only if its Install Task installed RKE2 (install, install push, join). The
# other tasks (install velero, install monitoring, save, push, uninstall) work
# on a cluster another deployment installed, so uninstalling them leaves RKE2,
# and what the task added, in place.
#
# Other workflows run stop too: a reinstall during an update ("Run automatic
# reinstall" or a reinstall list) and Heal. In those RKE2 stays as it is.

workflow="$(ctx workflow-id 2>/dev/null || echo unknown)"

case "${workflow}" in
    uninstall)
        case "${RUN_ARG:-}" in
            install|"install push"|join)
                if [ -x ~/rke2_installer.sh ]; then
                    ctx logger info "Uninstalling RKE2 (Install Task '${RUN_ARG}')."
                    cd ~ && sudo -E ./rke2_installer.sh uninstall
                else
                    ctx logger info "rke2_installer.sh not found in the home directory: nothing to uninstall."
                fi
                ;;
            *)
                ctx logger info "Install Task '${RUN_ARG:-}' didn't install RKE2: leaving RKE2 in place."
                ;;
        esac
        ;;
    *)
        ctx logger info "Keeping RKE2 and its data (${workflow} workflow): only uninstalling the deployment removes them."
        ;;
esac
