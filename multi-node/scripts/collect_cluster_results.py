from nativeedge import ctx
from nativeedge.manager import get_rest_client


def build_vm_entry(caps):
    """Build a standardized VM result dict from ServiceComponent capabilities."""
    return {
        'service_tag': caps.get('service_tag', ''),
        'hostname': caps.get('vm_hostname', ''),
        'primary_ip': caps.get('vm_primary_ip', ''),
        'vm_name_id': caps.get('vm_name_id', ''),
    }


def build_postcheck_entry(caps):
    """Build a postcheck result dict from env postcheck capabilities."""
    return {
        'rke2_running': caps.get('rke2_running', 'false'),
        'rke2_node_status': caps.get('rke2_node_status', 'N/A'),
    }


if __name__ == "__main__":
    client = get_rest_client()
    dep_id = ctx.deployment.id

    # --- Collect CP1 (base_vm) info ---
    base_instances = client.node_instances.list(
        deployment_id=dep_id, node_id='base_vm'
    )
    cp1_vm = {}
    for inst in base_instances:
        caps = inst.runtime_properties.get('capabilities', {})
        vm_name = caps.get('vm_name', '')
        if vm_name:
            cp1_vm = build_vm_entry(caps)
            cp1_vm['vm_name'] = vm_name
            break

    # CP1 postcheck info from env_postcheck
    postcheck_instances = client.node_instances.list(
        deployment_id=dep_id, node_id='env_postcheck'
    )
    cp1_postcheck = {}
    for inst in postcheck_instances:
        caps = inst.runtime_properties.get('capabilities', {})
        cp1_postcheck = {
            'rke2_running': caps.get('rke2_running', 'false'),
            'rke2_node_status': caps.get('rke2_node_status', 'N/A'),
            'rke2_api_url': caps.get('rke2_api_url', 'N/A'),
            'mgmt_ip': caps.get('mgmt_ip', ''),
        }
        break

    cp1_entry = {}
    cp1_entry.update(cp1_vm)
    cp1_entry.update(cp1_postcheck)

    # --- Collect additional CP nodes (add_cp_vm) ---
    control_plane_nodes = [cp1_entry] if cp1_entry else []

    try:
        cp_vm_instances = client.node_instances.list(
            deployment_id=dep_id, node_id='add_cp_vm'
        )
        cp_postcheck_instances = client.node_instances.list(
            deployment_id=dep_id, node_id='cp_env_postcheck'
        )
        sorted_cp_vms = sorted(cp_vm_instances, key=lambda ni: ni.id)
        sorted_cp_postchecks = sorted(
            cp_postcheck_instances, key=lambda ni: ni.id
        )

        for i, inst in enumerate(sorted_cp_vms):
            caps = inst.runtime_properties.get('capabilities', {})
            vm_name = caps.get('vm_name', '')
            entry = build_vm_entry(caps)
            entry['vm_name'] = vm_name

            if i < len(sorted_cp_postchecks):
                pc_caps = sorted_cp_postchecks[i].runtime_properties.get(
                    'capabilities', {}
                )
                entry.update(build_postcheck_entry(pc_caps))

            control_plane_nodes.append(entry)
    except Exception as e:
        ctx.logger.info(f"No additional CP nodes found: {e}")

    # --- Collect agent nodes (add_ag_vm) ---
    agent_nodes = []

    try:
        ag_vm_instances = client.node_instances.list(
            deployment_id=dep_id, node_id='add_ag_vm'
        )
        ag_postcheck_instances = client.node_instances.list(
            deployment_id=dep_id, node_id='ag_env_postcheck'
        )
        sorted_ag_vms = sorted(ag_vm_instances, key=lambda ni: ni.id)
        sorted_ag_postchecks = sorted(
            ag_postcheck_instances, key=lambda ni: ni.id
        )

        for i, inst in enumerate(sorted_ag_vms):
            caps = inst.runtime_properties.get('capabilities', {})
            vm_name = caps.get('vm_name', '')
            entry = build_vm_entry(caps)
            entry['vm_name'] = vm_name

            if i < len(sorted_ag_postchecks):
                pc_caps = sorted_ag_postchecks[i].runtime_properties.get(
                    'capabilities', {}
                )
                entry.update(build_postcheck_entry(pc_caps))

            agent_nodes.append(entry)
    except Exception as e:
        ctx.logger.info(f"No agent nodes found: {e}")

    # --- Build cluster info summary ---
    cluster_info = {
        'rke2_api_url': cp1_postcheck.get('rke2_api_url', 'N/A'),
        'mgmt_ip': cp1_postcheck.get('mgmt_ip', ''),
        'total_control_plane': len(control_plane_nodes),
        'total_agents': len(agent_nodes),
    }

    ctx.instance.runtime_properties['cluster_info'] = cluster_info
    ctx.instance.runtime_properties['control_plane_nodes'] = \
        control_plane_nodes
    ctx.instance.runtime_properties['agent_nodes'] = agent_nodes
    ctx.instance.update()

    ctx.logger.info(
        f"Cluster results collected: {cluster_info['total_control_plane']} "
        f"CP node(s), {cluster_info['total_agents']} agent node(s)"
    )
