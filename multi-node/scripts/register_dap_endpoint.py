import os

import requests

from nativeedge import ctx
from nativeedge.exceptions import NonRecoverableError
from nativeedge.manager import get_rest_client
from nativeedge.state import ctx_parameters as inputs


INVENTORY_URL = os.getenv('INVENTORY_URL', 'http://hzp-inventory-svc:80')
ENDPOINTS_API = f'{INVENTORY_URL}/api/v2/endpoints'


def get_env_postcheck_caps():
    """Retrieve env_postcheck runtime properties via REST client."""
    client = get_rest_client()
    dep_id = ctx.deployment.id

    instances = client.node_instances.list(
        deployment_id=dep_id, node_id='env_postcheck'
    )
    for inst in instances:
        caps = inst.runtime_properties.get('capabilities', {})
        if caps.get('rke2_running') == 'true':
            return caps

    raise NonRecoverableError(
        'env_postcheck capabilities not found or RKE2 is not running. '
        'Cannot register cluster as DAP infrastructure.'
    )


def find_existing_endpoint(name):
    """Check if an endpoint with this name already exists."""
    resp = requests.get(
        ENDPOINTS_API,
        params={'search': f'name={name}', 'only': 'id,name'}
    )
    if resp.status_code == 200:
        data = resp.json()
        results = data.get('results', [])
        for ep in results:
            if ep.get('name') == name:
                return ep.get('id')
    return None


def create_endpoint(name, description, host, port, ca_cert, token):
    """Create a Kubernetes endpoint in the DAP inventory."""
    payload = {
        'name': name,
        'description': description,
        'type': 'kubernetes',
        'credentials': {
            'host': host,
            'port': str(port),
            'ca_cert': ca_cert,
            'token': token,
        }
    }

    resp = requests.post(ENDPOINTS_API, json=payload)

    if resp.status_code == 201:
        return resp.json()

    raise NonRecoverableError(
        f'Failed to register DAP endpoint. '
        f'Status: {resp.status_code}, Response: {resp.text}'
    )


def delete_endpoint(endpoint_id):
    """Remove a Kubernetes endpoint from the DAP inventory."""
    resp = requests.delete(f'{ENDPOINTS_API}/{endpoint_id}')
    if resp.status_code not in (204, 404):
        ctx.logger.warning(
            f'Failed to delete DAP endpoint {endpoint_id}. '
            f'Status: {resp.status_code}, Response: {resp.text}'
        )
        return False
    return True


def register():
    """Register the RKE2 cluster as DAP external infrastructure."""
    register_flag = inputs.get('register_dap_infrastructure', False)
    if not register_flag:
        ctx.logger.info(
            'register_dap_infrastructure is false, skipping registration.'
        )
        ctx.instance.runtime_properties['dap_endpoint'] = {}
        ctx.instance.update()
        return

    dep_id = ctx.deployment.id
    caps = get_env_postcheck_caps()

    mgmt_ip = caps.get('mgmt_ip', '')
    ca_cert = caps.get('rke2_ca_cert', '')
    bearer_token = caps.get('bearer_token', '')

    if not mgmt_ip or not ca_cert or not bearer_token:
        raise NonRecoverableError(
            'Missing required cluster data for DAP registration. '
            f'mgmt_ip={bool(mgmt_ip)}, ca_cert={bool(ca_cert)}, '
            f'bearer_token={bool(bearer_token)}'
        )

    endpoint_name = inputs.get('dap_endpoint_name', '').strip() or dep_id
    description = f'RKE2 cluster: {endpoint_name} (deployment: {dep_id})'

    existing_id = find_existing_endpoint(endpoint_name)
    if existing_id:
        raise NonRecoverableError(
            f'DAP endpoint "{endpoint_name}" already exists '
            f'(id={existing_id}). Choose a unique name in the '
            f'dap_endpoint_name input and retry.'
        )

    ctx.logger.info(
        f'Registering RKE2 cluster as DAP infrastructure: '
        f'name={endpoint_name}, host={mgmt_ip}'
    )

    result = create_endpoint(
        name=endpoint_name,
        description=description,
        host=mgmt_ip,
        port='6443',
        ca_cert=ca_cert,
        token=bearer_token,
    )

    endpoint_info = {
        'id': result.get('id', ''),
        'name': result.get('name', ''),
        'state': result.get('state', ''),
    }
    ctx.instance.runtime_properties['dap_endpoint'] = endpoint_info
    ctx.instance.update()

    ctx.logger.info(
        f'DAP endpoint registered: id={endpoint_info["id"]}, '
        f'name={endpoint_info["name"]}, state={endpoint_info["state"]}'
    )


def unregister():
    """Remove the RKE2 cluster from DAP external infrastructure."""
    endpoint_info = ctx.instance.runtime_properties.get('dap_endpoint', {})
    endpoint_id = endpoint_info.get('id', '')

    if not endpoint_id:
        ctx.logger.info('No DAP endpoint to remove.')
        return

    ctx.logger.info(f'Removing DAP endpoint: id={endpoint_id}')
    if delete_endpoint(endpoint_id):
        ctx.logger.info(f'DAP endpoint {endpoint_id} removed.')
    else:
        ctx.logger.warning(f'DAP endpoint {endpoint_id} removal failed.')


if __name__ == '__main__':
    operation = ctx.operation.name
    if operation.endswith('.stop') or operation.endswith('.delete'):
        unregister()
    else:
        register()
