import json
import crypt
import base64
import yaml

from nativeedge import ctx
from nativeedge.exceptions import NonRecoverableError
from nativeedge.state import ctx_parameters as inputs


def build_network_settings(primary_segment, primary_port_forwards, vm_add_nics):
    """Build network_settings list for primary NIC + additional NICs.

    Replicates logic from prepare_network_settings.py with port forwarding
    support on both primary and additional NICs.
    """
    network_settings = []

    # Primary NIC (VNIC0)
    if not primary_segment:
        raise NonRecoverableError(
            'Primary network segment (vnic_0) is required.')
    network_setting = {
        'name': 'VNIC0',
        'segment_name': primary_segment
    }
    if primary_port_forwards:
        network_setting['port_fwd_rules'] = primary_port_forwards
    network_settings.append(network_setting)

    # Additional NICs (VNIC1+)
    for idx, nic in enumerate(vm_add_nics):
        segment = nic.get('segment_name', '')
        if not segment:
            ctx.logger.debug(
                f'Skipping additional NIC {idx + 1} - no segment name.')
            continue
        vnic_name = f'VNIC{idx + 1}'
        network_setting = {
            'name': vnic_name,
            'segment_name': segment
        }

        # Handle NAT port forwarding
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

    ctx.logger.debug(f'Number of VNICs attached: {len(network_settings)}')
    return network_settings


def build_netplan_yaml(use_dhcp, static_ip, use_gateway, gateway,
                       use_dns, dns, vm_add_nics):
    """Build netplan YAML for primary NIC + additional NICs + management.

    Python-based approach (no Jinja2 template) matching the pattern in
    prepare_additional_vm.py but adapted for base VM individual inputs.
    """
    netplan = {
        'network': {
            'version': 2,
            'renderer': 'networkd',
            'ethernets': {}
        }
    }

    # --- Primary NIC (enp1s0) ---
    if not use_dhcp:
        if not static_ip:
            raise NonRecoverableError(
                'Primary NIC: if DHCP not used, static_ip must be provided.')
        if not gateway:
            raise NonRecoverableError(
                'Primary NIC: if DHCP not used, gateway must be provided.')

    # Parse DNS
    dns_list = []
    if dns:
        if isinstance(dns, str):
            dns_list = [s.strip() for s in dns.split(',') if s.strip()]
        elif isinstance(dns, list):
            dns_list = dns

    primary_conf = {'dhcp-identifier': 'mac', 'dhcp4': use_dhcp}
    if not use_dhcp:
        if static_ip:
            primary_conf['addresses'] = [static_ip]
        if use_dns and dns_list:
            primary_conf['nameservers'] = {'addresses': dns_list}
        if use_gateway and gateway:
            primary_conf['routes'] = [{'to': 'default', 'via': gateway}]

    netplan['network']['ethernets']['enp1s0'] = primary_conf

    # --- Additional NICs (enp2s0, enp3s0, ...) ---
    for idx, nic in enumerate(vm_add_nics):
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

        # Validate
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

    # --- Management interface (always DHCP, suppress routes) ---
    mgmt_interface = f'enp{len(vm_add_nics) + 2}s0'
    netplan['network']['ethernets'][mgmt_interface] = {
        'dhcp4': True,
        'dhcp4-overrides': {'use-routes': False}
    }

    netplan_yaml = yaml.dump(netplan, default_flow_style=False)
    return base64.b64encode(netplan_yaml.encode('utf-8')).decode('utf-8')


def hash_password(plain_password):
    """Hash a plain password using SHA-512 crypt."""
    return crypt.crypt(plain_password, crypt.mksalt(crypt.METHOD_SHA512))


def build_cloudinit_config(vm_hostname, vm_user_name, hashed_passwd,
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
                'passwd': hashed_passwd,
                'lock_passwd': False,
                'shell': '/bin/bash',
                'ssh_authorized_keys': [ssh_public_key]
            }
        ]
    }


def deep_merge(base, override):
    """Recursively merge override into base.

    - Dicts: recursively merged
    - Lists: concatenated
    - Scalars: override wins
    """
    if not override:
        return base
    result = dict(base)
    for key, val in override.items():
        if key in result:
            if isinstance(result[key], dict) and isinstance(val, dict):
                result[key] = deep_merge(result[key], val)
            elif isinstance(result[key], list) and isinstance(val, list):
                result[key] = result[key] + val
            else:
                result[key] = val
        else:
            result[key] = val
    return result


if __name__ == "__main__":
    # Read inputs
    primary_segment = inputs.get('primary_segment', '')
    primary_port_forwards = inputs.get('primary_port_forwards', [])
    vm_add_nics = inputs.get('vm_add_nics', [])
    use_dhcp = inputs.get('use_dhcp', True)
    static_ip = inputs.get('static_ip', '')
    use_gateway = inputs.get('use_gateway', False)
    gateway = inputs.get('gateway', '')
    use_dns = inputs.get('use_dns', False)
    dns = inputs.get('dns', '')
    vm_hostname = inputs.get('vm_hostname', 'edgehost')
    vm_user_name = inputs.get('vm_user_name', 'edgeuser')
    vm_password = inputs.get('vm_password', '')
    ssh_public_key = inputs.get('ssh_public_key', '')
    cloudinit_override = inputs.get('cloudinit_override', {})

    # 1. Build network settings
    network_settings = build_network_settings(
        primary_segment, primary_port_forwards, vm_add_nics
    )
    ctx.instance.runtime_properties['network_settings'] = network_settings

    # 2. Build netplan YAML (base64)
    netplan_b64 = build_netplan_yaml(
        use_dhcp, static_ip, use_gateway, gateway,
        use_dns, dns, vm_add_nics
    )

    # 3. Hash password
    hashed_passwd = hash_password(vm_password)
    ctx.instance.runtime_properties['hashed_vm_passwd'] = hashed_passwd
    ctx.logger.info('Password hashed and set as runtime property for multi-node VMs')

    # 4. Build cloud-init config
    cloudinit_config = build_cloudinit_config(
        vm_hostname, vm_user_name, hashed_passwd,
        ssh_public_key, netplan_b64
    )

    # 5. Merge with optional cloudinit override
    if cloudinit_override:
        cloudinit_config = deep_merge(cloudinit_config, cloudinit_override)
        ctx.logger.info('Merged user cloudinit override into config.')

    ctx.instance.runtime_properties['cloudinit_config'] = cloudinit_config

    ctx.instance.update()
    ctx.logger.info(
        f"Base VM prep complete: {len(network_settings)} VNIC(s), "
        f"hostname='{vm_hostname}'"
    )
