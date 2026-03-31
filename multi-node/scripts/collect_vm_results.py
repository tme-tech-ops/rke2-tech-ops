from nativeedge import ctx
from nativeedge.manager import get_rest_client


def build_vm_entry(caps):
    """Build a standardized VM result dict from ServiceComponent capabilities."""
    return {
        'service_tag': caps.get('service_tag', ''),
        'hostname': caps.get('vm_hostname', ''),
        'primary_ip': caps.get('vm_primary_ip', ''),
        # 'tap_ip': caps.get('tap_ip', ''),
        # 'vm_add_nics': caps.get('vm_add_nics', 'N/A'),
        # 'vm_add_disks': caps.get('vm_add_disks', []),
        # 'vm_add_passthrough': caps.get('vm_add_passthrough', {}),
        # 'proxy_target_id': caps.get('proxy_target_id', ''),
    }


if __name__ == "__main__":
    client = get_rest_client()

    # Collect base VM results
    base_instances = client.node_instances.list(
        deployment_id=ctx.deployment.id,
        node_id='base_vm'
    )
    base_vm = {}
    for inst in base_instances:
        caps = inst.runtime_properties.get('capabilities', {})
        vm_name = caps.get('vm_name', '')
        if vm_name:
            base_vm[vm_name] = build_vm_entry(caps)
            # base_vm['vm_name'] = vm_name
            break

    ctx.instance.runtime_properties['base_vm'] = base_vm

    # Collect additional VM results
    add_instances = client.node_instances.list(
        deployment_id=ctx.deployment.id,
        node_id='add_vm'
    )
    sorted_instances = sorted(add_instances, key=lambda ni: ni.id)

    additional_vm = {}
    for inst in sorted_instances:
        caps = inst.runtime_properties.get('capabilities', {})
        vm_name = caps.get('vm_name', '')
        if vm_name:
            additional_vm[vm_name] = build_vm_entry(caps)

    ctx.instance.runtime_properties['additional_vm'] = additional_vm
    ctx.instance.update()

    ctx.logger.info(
        f"Collected base VM: {base_vm.get('vm_name', 'N/A')}, "
        f"additional VMs: {list(additional_vm.keys())}"
    )
