import json
import base64
import yaml

from nativeedge import ctx
from nativeedge.exceptions import NonRecoverableError
from nativeedge.state import ctx_parameters as inputs
from nativeedge.manager import get_rest_client


def get_instance_index():
    """Determine this instance's index within the scaling group."""
    client = get_rest_client()
    node_instances = client.node_instances.list(
        deployment_id=ctx.deployment.id,
        node_id=ctx.node.id
    )
    sorted_instances = sorted(node_instances, key=lambda ni: ni.id)
    for i, ni in enumerate(sorted_instances):
        if ni.id == ctx.instance.id:
            return i
    raise NonRecoverableError(
        f"Could not find instance {ctx.instance.id} in node instances list."
    )


def get_service_tag_from_deployment(client, deployment_id):
    """Resolve ece_service_tag capability from a deployment."""
    try:
        caps = client.deployments.capabilities.get(deployment_id)
        cap_values = caps.get('capabilities', caps)
        if isinstance(cap_values, dict) and 'ece_service_tag' in cap_values:
            tag = cap_values['ece_service_tag']
            if isinstance(tag, dict) and 'value' in tag:
                return tag['value']
            return tag
        raise NonRecoverableError(
            f"Deployment '{deployment_id}' does not have "
            f"'ece_service_tag' capability."
        )
    except Exception as e:
        raise NonRecoverableError(
            f"Failed to get ece_service_tag from deployment "
            f"'{deployment_id}': {e}"
        )


def build_network_settings(vm_config, add_nics):
    """Build network_settings list for primary NIC + additional NICs."""
    network_settings = []

    segment_name = vm_config.get('segment_name', '')
    if not segment_name:
        raise NonRecoverableError(
            "segment_name is required for primary NIC (VNIC0)."
        )
    primary_setting = {
        'name': 'VNIC0',
        'segment_name': segment_name
    }

    if vm_config.get('use_nat', False):
        pf_rules = vm_config.get('port_forward_rules', [])
        if pf_rules:
            primary_setting['port_fwd_rules'] = pf_rules

    network_settings.append(primary_setting)

    for idx, nic in enumerate(add_nics):
        segment = nic.get('segment_name', '')
        if not segment:
            raise NonRecoverableError(
                f"segment_name is required for additional NIC "
                f"{idx + 1} (VNIC{idx + 1})."
            )
        vnic_name = f'VNIC{idx + 1}'
        network_setting = {
            'name': vnic_name,
            'segment_name': segment
        }

        pf_rules_raw = nic.get('port_forward_rules', '')
        if nic.get('use_nat', False) and pf_rules_raw:
            if isinstance(pf_rules_raw, str):
                try:
                    pf_rules = json.loads(pf_rules_raw)
                    network_setting['port_fwd_rules'] = pf_rules
                except json.JSONDecodeError:
                    ctx.logger.warning(
                        f'Invalid JSON for port_forward_rules on {vnic_name}')
            elif isinstance(pf_rules_raw, list):
                network_setting['port_fwd_rules'] = pf_rules_raw

        network_settings.append(network_setting)

    return network_settings


def build_netplan_yaml(vm_config, add_nics, mgmt_interface):
    """Build netplan YAML for primary NIC + additional NICs + management."""
    netplan = {
        'network': {
            'version': 2,
            'renderer': 'networkd',
            'ethernets': {}
        }
    }

    use_dhcp = vm_config.get('use_dhcp', True)
    static_ip = vm_config.get('static_ip', '')
    use_gateway = vm_config.get('use_gateway', False)
    gateway = vm_config.get('gateway', '')
    use_dns = vm_config.get('use_dns', False)
    dns_list = vm_config.get('dns', [])
    if isinstance(dns_list, str) and dns_list:
        dns_list = [s.strip() for s in dns_list.split(',') if s.strip()]

    if not use_dhcp:
        if not static_ip:
            raise NonRecoverableError(
                'Primary NIC: if DHCP not used, static_ip must be provided.')
        if use_gateway and not gateway:
            raise NonRecoverableError(
                'Primary NIC: gateway is required when use_gateway is true.')

    primary_conf = {'dhcp-identifier': 'mac', 'dhcp4': use_dhcp}
    if not use_dhcp:
        if static_ip:
            primary_conf['addresses'] = [static_ip]
        if use_dns and dns_list:
            primary_conf['nameservers'] = {'addresses': dns_list}
        if use_gateway and gateway:
            primary_conf['routes'] = [{'to': 'default', 'via': gateway}]

    netplan['network']['ethernets']['enp1s0'] = primary_conf

    for idx, nic in enumerate(add_nics):
        iface = f'enp{idx + 2}s0'
        nic_use_dhcp = nic.get('use_dhcp', True)
        nic_accept_routes = nic.get('accept_dhcp_routes', False)
        nic_static_ip = nic.get('static_ip', '')
        nic_use_gateway = nic.get('use_gateway', False)
        nic_gateway = nic.get('gateway', '')
        nic_route_dest = nic.get('route_destination', '')
        nic_use_dns = nic.get('use_dns', False)
        nic_dns_raw = nic.get('dns', '')

        if isinstance(nic_dns_raw, str) and nic_dns_raw:
            nic_dns_list = [s.strip() for s in nic_dns_raw.split(',')
                           if s.strip()]
        elif isinstance(nic_dns_raw, list):
            nic_dns_list = nic_dns_raw
        else:
            nic_dns_list = []

        nic_label = f'Additional NIC {idx + 1} ({iface})'

        if not nic_use_dhcp and not nic_static_ip:
            raise NonRecoverableError(
                f'{nic_label}: if DHCP not used, static_ip must be provided.')
        if nic_use_gateway:
            if not nic_gateway:
                raise NonRecoverableError(
                    f'{nic_label}: gateway is required when '
                    f'use_gateway is true.')
            if not nic_route_dest:
                raise NonRecoverableError(
                    f'{nic_label}: route_destination is required when '
                    f'use_gateway is true (e.g. 10.20.0.0/16).')
            if nic_route_dest == '0.0.0.0/0':
                raise NonRecoverableError(
                    f'{nic_label}: route_destination cannot be 0.0.0.0/0. '
                    f'Only the primary NIC should have a default route.')

        nic_conf = {'dhcp-identifier': 'mac', 'dhcp4': nic_use_dhcp}

        if nic_use_dhcp:
            if not nic_accept_routes:
                nic_conf['dhcp4-overrides'] = {'use-routes': False}
        else:
            if nic_static_ip:
                nic_conf['addresses'] = [nic_static_ip]
            if nic_use_dns and nic_dns_list:
                nic_conf['nameservers'] = {'addresses': nic_dns_list}
            if nic_use_gateway and nic_gateway:
                nic_conf['routes'] = [
                    {'to': nic_route_dest, 'via': nic_gateway}
                ]

        netplan['network']['ethernets'][iface] = nic_conf

    netplan['network']['ethernets'][mgmt_interface] = {
        'dhcp4': True,
        'dhcp4-overrides': {'use-routes': False}
    }

    netplan_yaml = yaml.dump(netplan, default_flow_style=False)
    return base64.b64encode(netplan_yaml.encode('utf-8')).decode('utf-8')


def build_additional_disks(add_disks):
    """Build additional_disks list for NativeEdgeVM node."""
    disks = []
    for d in add_disks:
        disks.append({
            'name': d['name'],
            'disk': d['disk'],
            'storage': d['storage'],
            'storage_unit': d.get('storage_unit', 'GB')
        })
    return disks


def build_cloudinit_config(vm_hostname, vm_user_name, hashed_vm_passwd,
                           ssh_public_key, netplan_b64):
    """Build the complete cloud-init configuration dict."""
    return {
        'hostname': vm_hostname,
        'runcmd': [
            'netplan apply',
            'systemctl restart sshd'
        ],
        'write_files': [
            {
                'content': netplan_b64,
                'encoding': 'b64',
                'path': '/etc/netplan/50-cloud-init.yaml'
            },
            {
                'content': 'ClientAliveInterval 1800\nClientAliveCountMax 3\n',
                'path': '/etc/ssh/sshd_config',
                'append': True
            }
        ],
        'disable_root_opts':
            'no-port-forwarding,no-agent-forwarding,no-X11-forwarding',
        'disable_root': False,
        'ssh_pwauth': True,
        'ssh_authorized_keys': [ssh_public_key],
        'users': [
            {
                'name': vm_user_name,
                'sudo': ['ALL=(ALL) NOPASSWD:ALL'],
                'groups': 'users, admin',
                'passwd': hashed_vm_passwd,
                'lock_passwd': False,
                'shell': '/bin/bash',
                'ssh_authorized_keys': [ssh_public_key]
            }
        ]
    }


if __name__ == "__main__":
    ssh_public_key = inputs.get('ssh_public_key', '')
    hashed_vm_passwd = inputs.get('hashed_vm_passwd', '')
    vm_user_name = inputs.get('cp_1_vm_user_name', 'edgeuser')

    if hashed_vm_passwd:
        ctx.logger.info('Received hashed password from base VM configuration')
    else:
        ctx.logger.warning(
            'No hashed password received from base VM - '
            'SSH password authentication may fail')

    # Hardware from profile
    vcpus = inputs.get('ag_vcpus', 4)
    memory_size = inputs.get('ag_memory_size', '8GB')
    os_disk_size = inputs.get('ag_os_disk_size', '100GB')
    disk_controller = inputs.get('ag_disk_controller', 'VIRTIO')

    my_index = get_instance_index()
    vm_number = my_index + 1  # index 0 = AG1, index 1 = AG2, etc.
    prefix = f'ag_{vm_number}_'
    dep_id_key = f'ag_deployment_id_{vm_number:02d}'

    ctx.logger.info(
        f"Instance index {my_index}: configuring AG #{vm_number} "
        f"(input prefix: '{prefix}')"
    )

    # Resolve ece_service_tag from deployment_id
    deployment_id = inputs.get(dep_id_key)
    if not deployment_id:
        raise NonRecoverableError(
            f"No deployment_id found for key '{dep_id_key}'. "
            f"Ensure {dep_id_key} is provided."
        )

    client = get_rest_client()
    ece_service_tag = get_service_tag_from_deployment(client, deployment_id)

    # Read per-VM inputs
    vm_name = inputs.get(f'{prefix}name', f'rke2-ag-{vm_number:02d}')
    vm_hostname = inputs.get(f'{prefix}hostname', f'rke2ag-{vm_number:02d}')
    disk = inputs.get(f'{prefix}disk_wrapper', '/DataStore0')

    ctx.logger.info(
        f"AG #{vm_number}: '{vm_name}' on endpoint '{ece_service_tag}'"
    )

    # Build vm_config dict for network functions
    vm_config = {
        'segment_name': inputs.get(f'{prefix}vnic_0_segment_name', ''),
        'use_dhcp': inputs.get(f'{prefix}use_dhcp', True),
        'static_ip': inputs.get(f'{prefix}static_ip', ''),
        'use_gateway': inputs.get(f'{prefix}use_gateway', False),
        'gateway': inputs.get(f'{prefix}gateway', ''),
        'use_dns': inputs.get(f'{prefix}use_dns', False),
        'dns': inputs.get(f'{prefix}dns', []),
        'use_nat': inputs.get(f'{prefix}use_nat', False),
        'port_forward_rules': inputs.get(f'{prefix}port_forward_rules', []),
    }

    my_add_nics = inputs.get(f'{prefix}vm_add_nics', [])
    my_add_disks = inputs.get(f'{prefix}additional_disks', [])

    usb = inputs.get(f'{prefix}usb_wrapper', [])
    gpu = inputs.get(f'{prefix}gpu_wrapper', [])
    pcie = inputs.get(f'{prefix}pcie_wrapper', [])
    video = inputs.get(f'{prefix}video', [])
    serial_port = inputs.get(f'{prefix}serial_port_wrapper', [])

    ctx.logger.info(
        f"AG #{vm_number}: {len(my_add_nics)} additional NIC(s), "
        f"{len(my_add_disks)} additional disk(s), "
        f"{len(usb) + len(gpu) + len(pcie) + len(video) + len(serial_port)} "
        f"passthrough device(s)"
    )

    # Set runtime properties for ServiceComponent inputs
    ctx.instance.runtime_properties['ece_service_tag'] = ece_service_tag
    ctx.instance.runtime_properties['vm_name'] = vm_name
    ctx.instance.runtime_properties['vm_hostname'] = vm_hostname
    ctx.instance.runtime_properties['vcpus'] = vcpus
    ctx.instance.runtime_properties['memory_size'] = memory_size
    ctx.instance.runtime_properties['os_disk_size'] = os_disk_size
    ctx.instance.runtime_properties['disk'] = disk
    ctx.instance.runtime_properties['disk_controller'] = disk_controller

    # Build network settings
    ctx.instance.runtime_properties['network_settings'] = \
        build_network_settings(vm_config, my_add_nics)

    # Build netplan and cloud-init config
    mgmt_interface = f'enp{2 + len(my_add_nics)}s0'
    netplan_b64 = build_netplan_yaml(vm_config, my_add_nics, mgmt_interface)

    cloudinit_config = build_cloudinit_config(
        vm_hostname, vm_user_name, hashed_vm_passwd,
        ssh_public_key, netplan_b64
    )
    ctx.instance.runtime_properties['cloudinit_config'] = cloudinit_config

    # Build additional disks
    ctx.instance.runtime_properties['additional_disks'] = \
        build_additional_disks(my_add_disks)

    # Set passthrough device lists
    ctx.instance.runtime_properties['usb'] = usb
    ctx.instance.runtime_properties['serial_port'] = serial_port
    ctx.instance.runtime_properties['gpu'] = gpu
    ctx.instance.runtime_properties['video'] = video
    ctx.instance.runtime_properties['pcie'] = pcie

    ctx.instance.update()
    ctx.logger.info(
        f"Instance {my_index}: runtime properties set for "
        f"AG #{vm_number} '{vm_name}' on endpoint '{ece_service_tag}'"
    )
