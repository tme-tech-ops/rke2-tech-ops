"""Makes an update the cluster's VMs must not take fail visibly.

Two kinds of change are refused, and the VMs stay as they are:

- A disk that would shrink. The utility VM leaves the VM alone (the Endpoint
  refuses to shrink a disk, and a failed VM update can turn into delete +
  create of the VM with "Run automatic reinstall").
- A control plane profile change (vCPUs, memory, OS disk) when the cluster has
  more than one control plane. The VMs would restart at the same time and etcd
  would lose its quorum. The control plane VMs keep their install-time sizes in
  the component inputs, so the change doesn't reach them. (CP1 keeps them from
  prep_config's record; a cluster created before 1.2 has none, so its CP1
  follows the profile while CP2-3 keep theirs: one restart, quorum kept.)
  Disks don't need this: only CP1's disks can change, so at most one control
  plane restarts for a disk change.

This node makes the reason visible: its check_drift reports it as drift, so its
update operation runs and fails with the reason; with automatic reinstall it is
reinstalled instead, and its create fails with the same reason.

The requested sizes come from the operation inputs (evaluated with the update's
new inputs); the current ones from each VM's record of what was last applied
(expected_configuration of the utility deployment's `vm` node).

It also warns, at the start of an update, when an app deployed on a VM will
block it (see force_warnings). Warnings never fail the update.

The same script runs as check_drift, update and create (ctx.operation.name).
"""
import re

from dell import ctx
from dell.exceptions import NonRecoverableError
from dell.manager import get_rest_client
from dell.state import ctx_parameters as inputs

ACTIVE = ("pending", "queued", "started", "scheduled")
UNITS = {"KB": 2**10, "MB": 2**20, "GB": 2**30, "TB": 2**40, "PB": 2**50}
END_STATES = ("deployed", "uninstalled", "uninstall_cancelled", "install_cancelled")
VM_NODES = ("base_vm", "add_cp_vm", "add_ag_vm")


def to_bytes(size, unit=None):
    if isinstance(size, int) and not unit:
        return size
    if unit:
        size = f"{size}{unit}"
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMGTP]B)\s*", str(size or "").upper())
    return int(float(match.group(1)) * UNITS[match.group(2)]) if match else None


def disk_sizes(disks, requested=False):
    """{disk name: bytes}. The VM record stores bytes without a unit; requested
    disks give a size in storage_unit (GB when it's left out)."""
    return {d.get("name"): (d["storage"] if not requested and "storage_unit" not in d
                            and isinstance(d.get("storage"), int)
                            else to_bytes(d.get("storage"), d.get("storage_unit") or "GB"))
            for d in disks or [] if isinstance(d, dict)}


def updating(client):
    return any(e.get("workflow_id") == "update" and e.get("status") in ACTIVE
               for e in client.executions.list(deployment_id=ctx.deployment.id,
                                                _include=["workflow_id", "status"]))


def vm_deployments(client):
    """Ids of this deployment's VM deployments (the utility components)."""
    found = []
    for node_id in VM_NODES:
        for inst in client.node_instances.list(deployment_id=ctx.deployment.id, node_id=node_id):
            child_id = ((inst.runtime_properties or {}).get("deployment") or {}).get("id")
            if child_id:
                found.append(child_id)
    return found


def applied_configs(client, children):
    """{vm name: expected_configuration} of this deployment's VMs."""
    found = {}
    for child_id in children:
        for vm in client.node_instances.list(deployment_id=child_id, node_id="vm"):
            config = (vm.runtime_properties or {}).get("expected_configuration") or {}
            if config.get("name"):
                found[config["name"]] = config
    return found


def shrinks(requested, applied):
    """Disks the update would make smaller, per VM."""
    found = []
    for name, config in applied.items():
        want = requested.get(name)
        if not want:
            continue
        new = to_bytes(want.get("storage"))
        old = to_bytes((config.get("resource_constraints") or {}).get("storage"))
        if new and old and new < old:
            found.append(f"{name}: OS disk {old // 2**30}GB -> {new // 2**30}GB")
        new_disks = disk_sizes(want.get("disks") if want.get("add_disks") else [], requested=True)
        for disk, old_size in disk_sizes(config.get("additional_disks")).items():
            new_size = new_disks.get(disk)
            if new_size and old_size and new_size < old_size:
                found.append(f"{name}: disk {disk} {old_size // 2**30}GB -> {new_size // 2**30}GB")
    return found


def profile_changes(profile, cp_names, applied):
    """Control plane VMs whose size differs from the requested profile."""
    want = {"vCPUs": profile.get("vcpus"), "memory": to_bytes(profile.get("memory")),
            "OS disk": to_bytes(profile.get("storage"))}
    found = []
    for name in cp_names:
        limits = (applied.get(name) or {}).get("resource_constraints")
        if not limits:
            continue
        have = {"vCPUs": limits.get("cpu"), "memory": to_bytes(limits.get("memory")),
                "OS disk": to_bytes(limits.get("storage"))}
        changed = [key for key in want if want[key] and have[key] and want[key] != have[key]]
        if changed:
            found.append(f"{name} ({', '.join(changed)})")
    return found


def cp1_keeps_sizes(client):
    """Has CP1 an install-time size record (prep_config, 1.2 and later)?"""
    for inst in client.node_instances.list(deployment_id=ctx.deployment.id, node_id="prep_config"):
        if (inst.runtime_properties or {}).get("cp_vcpus") is not None:
            return True
    return False


def problem(client, children):
    vms = [vm for vm in inputs.get("vms") or [] if vm.get("name")]
    requested = {vm["name"]: vm for vm in vms}
    applied = applied_configs(client, children)
    reasons = []
    control_planes = int(inputs.get("control_planes") or 1)
    if control_planes > 1:
        cp_names = [vm["name"] for vm in vms if vm.get("role") == "control_plane"]
        changed = profile_changes(inputs.get("cp_profile") or {}, cp_names, applied)
        if changed:
            kept = ("The VMs were not changed" if cp1_keeps_sizes(client) else
                    "CP2-3 were not changed; this cluster was created before 1.2, so CP1 "
                    "follows the profile (one restart, quorum kept)")
            reasons.append(
                f"This cluster has {control_planes} control planes. A control plane profile change "
                f"(vCPUs, memory, OS disk) would restart them at the same time and etcd would lose "
                f"its quorum, so it isn't applied: {'; '.join(changed)}. {kept}; set the Control "
                f"Plane Profile back to the current sizes. Agent sizes and disks, and CP1's disks, "
                f"can change.")
    found = shrinks(requested, applied)
    if found:
        reasons.append("Disks can only grow (the Endpoint refuses to shrink them): " + "; ".join(found)
                       + ". The VMs were not changed; update again with sizes at least as large as now.")
    return " ".join(reasons) or None


def changes_something(record):
    """Does the update change an input or the blueprint? The record's new_inputs
    hold only the inputs the update sent; old_inputs hold all of them."""
    old, new = record.get("old_inputs") or {}, record.get("new_inputs") or {}
    return (any(old.get(name) != value for name, value in new.items())
            or record.get("old_blueprint_id") != record.get("new_blueprint_id")
            or record.get("old_blueprint_version") != record.get("new_blueprint_version"))


def needs_repair(deployment):
    """Would the component heal this VM deployment before updating it? Same
    rule as its check_status (validate_deployment_status)."""
    return (deployment.get("installation_status") != "active"
            or deployment.get("deployment_status") not in END_STATES
            or deployment.get("latest_execution_status") == "failed"
            or (deployment.get("unavailable_instances") or 0) > 0
            or (deployment.get("drifted_instances") or 0) > 0)


def force_warnings(client, children):
    """Apps deployed on a VM (its utility deployment is their "Deploy On"
    target) block that VM's update unless the update has Force, and block the
    repair (heal) of a failed VM deployment even with Force: the parent doesn't
    pass Force to a heal. DAP refuses either one and the parent retries for
    about 20 minutes before the update fails, so say it at the start."""
    params = client.executions.get(ctx.execution_id).parameters or {}
    record = {}
    if params.get("update_id"):
        record = client.deployment_updates.get(params["update_id"], _include=[
            "old_inputs", "new_inputs", "old_blueprint_id", "new_blueprint_id",
            "old_blueprint_version", "new_blueprint_version"])
    changes = changes_something(record) if record else True
    warnings = []
    for child_id in children:
        apps = client.deployments.list(_include=["id", "display_name"], filter_rules=[
            {"key": "csys-obj-parent", "values": [child_id], "operator": "any_of", "type": "label"}])
        if not apps:
            continue
        child = client.deployments.get(child_id, _include=[
            "id", "display_name", "installation_status", "deployment_status",
            "latest_execution_status", "unavailable_instances", "drifted_instances"])
        name = child.get("display_name") or child_id
        on_it = ", ".join(app.get("display_name") or app.get("id") for app in apps)
        if needs_repair(child):
            warnings.append(
                f"The VM deployment {name} needs a repair and has {on_it} deployed on it. DAP "
                f"refuses that repair (heal) while an app is deployed on it, even with Force, so if "
                f"this update changes that VM it fails after about 20 minutes. Cancel this update, "
                f"run Heal with Force on {name}, then update again.")
        elif changes and not params.get("force"):
            warnings.append(
                f"{on_it} is deployed on the VM deployment {name}. If this update changes that VM, "
                f"it needs Force: DAP refuses it otherwise and the update fails after about 20 "
                f"minutes. Cancel this update and run it again with Force ticked (Advanced).")
    return warnings


def main():
    op = ctx.operation.name.split(".")[-1]
    reason = None
    try:
        client = get_rest_client()
        if updating(client):  # not install, nor the check_drift workflow
            children = vm_deployments(client)
            reason = problem(client, children)
            if op == "check_drift" and not reason:
                try:
                    for warning in force_warnings(client, children):
                        ctx.logger.warning(f"update checks: {warning}")
                except Exception as err:
                    ctx.logger.warning(f"update checks: could not check the apps on the VMs ({err})")
    except Exception as err:  # API not reachable: don't block the update
        ctx.logger.warning(f"update checks: could not check this update ({err})")
        reason = None
    if op == "check_drift":
        ctx.logger.info(f"update checks: {inputs.get('control_planes')} control plane(s), "
                        f"{inputs.get('agents')} agent(s)")
        if reason:
            ctx.logger.warning(f"update checks: {reason}")
            ctx.returns({"resource_id": "update_checks", "diff_count": 1, "diff": reason})
        else:
            ctx.returns(None)
    elif reason:
        raise NonRecoverableError(reason)
    else:
        ctx.logger.info(f"update checks: {op}: passed")


main()
