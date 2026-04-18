# rke2-tech-ops

Automated RKE2 Kubernetes deployment blueprints for the Dell Automation Platform (DAP) Orchestrator. This repository provides two blueprint entry points for deploying RKE2 clusters on Dell NativeEdge infrastructure: a **multi-node** blueprint that provisions VMs and installs a full cluster in a single deployment, and a **standalone** blueprint that installs RKE2 onto an existing edge-cloud-init VM.

Both blueprints leverage the [Fabric plugin](https://docs.getcloudify.org/latest/working_with/official_plugins/configuration/fabric/) to execute the [rke2_installer.sh](https://github.com/Chubtoad5/rke2-installer) script over SSH, supporting online, air-gapped, and private-registry deployment models.

> **Disclaimer:** This is a community-driven, open-source project provided as-is with no warranty or support obligations. It is not officially affiliated with, endorsed by, or supported by Dell Technologies. Use at your own risk. Contributions and feedback are welcome.

---

## Table of Contents

- [Multi-Node Deployment](#multi-node-deployment)
  - [Overview](#multi-node-overview)
  - [Prerequisites](#multi-node-prerequisites)
  - [Basic Deployment Inputs](#basic-deployment-inputs)
  - [Advanced Deployment Inputs](#advanced-deployment-inputs)
  - [Control Plane Profile Inputs](#control-plane-profile-inputs)
  - [Agent Node Profile Inputs](#agent-node-profile-inputs)
  - [Per-Node Inputs](#per-node-inputs)
  - [Deployment Scenarios](#deployment-scenarios)
    - [Single-Node Cluster](#single-node-cluster)
    - [Control-Plane Only (3 Nodes)](#control-plane-only-3-nodes)
    - [Control-Plane with Agent Nodes](#control-plane-with-agent-nodes)
  - [Deployment Outputs](#multi-node-deployment-outputs)
  - [Technical Details](#multi-node-technical-details)
- [Standalone Deployment](#standalone-deployment)
  - [Overview](#standalone-overview)
  - [Prerequisites](#standalone-prerequisites)
  - [RKE2 Cluster Configuration Inputs](#rke2-cluster-configuration-inputs)
  - [Velero Backup Configuration Inputs](#velero-backup-configuration-inputs)
  - [Monitoring Configuration Inputs](#monitoring-configuration-inputs)
  - [Environment Configuration Inputs](#environment-configuration-inputs)
  - [Install Tasks](#install-tasks)
  - [Deployment Outputs](#standalone-deployment-outputs)
  - [Technical Details](#standalone-technical-details)
- [Input Examples](#input-examples)
  - [Multi-Node Examples](#multi-node-examples)
  - [Standalone Examples](#standalone-examples)
- [References](#references)

---

## Multi-Node Deployment

**Blueprint:** `rke2_tech_ops_multi-node.yaml`

### Multi-Node Overview

The multi-node blueprint provisions one or more VMs on a Dell NativeEdge Endpoint and deploys a complete RKE2 Kubernetes cluster in a single orchestrated workflow. It supports up to 3 control-plane nodes and up to 6 agent (worker) nodes.

The workflow performs the following steps:

1. Generates SSH key pairs for VM access
2. Downloads and validates the OS image binary
3. Prepares cloud-init and network configuration for the base (first control-plane) VM
4. Deploys the base VM using the `edge-cloudinit-utility-vm` sub-blueprint
5. Transfers and executes the `rke2_installer.sh` script on the base VM
6. Collects cluster credentials (API URL, join token, CA certificate, bearer token)
7. For multi-node clusters: provisions additional control-plane and agent VMs in parallel, joining each to the cluster
8. Collects and exposes cluster-wide results
9. Optionally registers the cluster as external infrastructure in DAP

### Multi-Node Prerequisites

- A Dell NativeEdge Endpoint registered in DAP
- The `edge-cloudinit-utility-vm` blueprint uploaded to the DAP Orchestrator
- An OS image secret configured in the DAP secret store (binary configuration type)
- A VM password secret configured in the DAP secret store (password type)
- Network connectivity between the Endpoint and the internet (or a configured offline archive / private registry)

### Basic Deployment Inputs

These inputs appear in the **Basic Deployment Configuration** group.

| Display Label | Input | Type | Default | Description |
|---|---|---|---|---|
| RKE2 Version | `rke2_version` | string | `v1.34.5+rke2r1` | RKE2 Kubernetes version to install |
| Number of Control Plane Nodes | `number_of_control_plane` | integer | `1` | Number of control-plane nodes (1 or 3) |
| Number of Agent (Worker) Nodes | `number_of_agent_nodes` | integer | `0` | Number of agent/worker nodes (0--6) |
| OS Image Secret | `edge_os_image_secret` | secret_key | -- | Secret containing OS image URL, credentials, and version |
| OS Type | `os_type` | string | `UBUNTU22.04` | VM operating system type |
| VM Username | `cp_1_vm_user_name` | string | `edgeuser` | Username for all cluster VMs |
| VM Password | `cp_1_vm_password` | secret_key | -- | Secret containing the VM password |
| Install NGINX Ingress | `install_ingress` | boolean | `false` | Install the RKE2 NGINX ingress controller |
| Install ServiceLB | `install_servicelb` | boolean | `false` | Install Klipper service load balancer |
| Install Local Path Provisioner | `install_local_path_provisioner` | boolean | `false` | Install Rancher local-path-provisioner storage class |
| Local Path Provisioner Version | `local_path_provisioner_version` | string | `v0.0.32` | Version (shown when provisioner is enabled) |
| Install DNS Utility | `install_dns_utility` | boolean | `false` | Install Kubernetes DNS utility container |
| TLS SAN | `tls_san` | string | `""` | Additional TLS SAN (FQDN or IP) for the API server certificate |
| Use Private Registry | `use_registry` | boolean | `false` | Enable private container registry for RKE2 images |
| Registry Authentication Secret | `registry_secret` | secret_key | -- | Registry auth secret (shown when registry is enabled) |
| Registry URL | `registry_url` | string | `""` | Registry URL, e.g. `myregistry.lab:5000` (shown when registry is enabled) |
| Push Images to Registry | `push_images` | boolean | `false` | Push RKE2 images to the private registry (shown when registry is enabled) |
| VM Firmware | `firmware_type` | string | `BIOS` | Enable UEFI firmware for all VMs (default is BIOS) |
| Secure Boot | `secure_boot` | boolean | `false` | Enable Secure Boot for all VMs (shown when UEFI is enabled) |
| Virtual TPM (vTPM) | `vtpm` | boolean | `false` | Enable vTPM for all VMs (shown when UEFI is enabled) |

### Advanced Deployment Inputs

These inputs appear in the **Advanced Deployment Configuration** group.

| Display Label | Input | Type | Default | Description |
|---|---|---|---|---|
| CNI Plugin | `cni_type` | string | `canal` | CNI plugin: `calico`, `canal`, `cilium`, or `none` |
| Cluster CIDR | `cluster_cidr` | string | `10.42.0.0/16` | Pod network CIDR range |
| Service CIDR | `service_cidr` | string | `10.43.0.0/16` | Service network CIDR range |
| Max Pods Per Node | `max_pods` | integer | `110` | Maximum pods per node |
| RKE2 Data Path | `rke2_data` | string | `default` | RKE2 data path (`default` = `/var/lib/rancher/rke2`) |
| Kubelet Data Path | `kubelet_data` | string | `default` | Kubelet data path (`default` = `/var/lib/kubelet`) |
| PVC Data Path | `pvc_data` | string | `default` | PVC storage path (`default` = `/opt/local-path-provisioner`) |
| Airgapped Mode | `offline_mode` | boolean | `false` | Enable air-gapped installation from an offline archive |
| Offline Binary Configuration Secret | `offline_binary_secret` | secret_key | -- | Offline archive binary secret (shown when offline mode is enabled) |
| Enable CIS Hardening | `enable_cis` | boolean | `false` | Enable CIS Kubernetes hardening profile |
| Utility VM Blueprint Name | `utility_blueprint_id` | string | `edge-cloudinit-utility-vm` | Name of the uploaded edge-cloudinit utility VM blueprint |
| Script URL | `script_url` | string | *(GitHub URL)* | URL of the `rke2_installer.sh` script |
| Log Output to hide | `hide_log_output` | list | `["stdout"]` | Log output to suppress: `stdout`, `stderr`, or `both` |
| Debug Logging | `debug` | integer | `1` | Debug logging (0 = off, 1 = on) |
| Service Account Namespace | `sa_namespace` | string | `kube-system` | Namespace for the DAP service account and bearer token |
| Register as DAP Infrastructure | `register_dap_infrastructure` | boolean | `false` | Register the cluster as external Kubernetes infrastructure in DAP |
| DAP Endpoint Name | `dap_endpoint_name` | string | `""` | Human-readable endpoint name in DAP inventory (shown when DAP registration is enabled) |

### Control Plane Profile Inputs

These inputs appear in the **Control Plane Profile** group and apply to all control-plane VMs.

| Display Label | Input | Type | Default | Description |
|---|---|---|---|---|
| Taint Control Plane | `control_plane_taint` | boolean | `false` | Taint control-plane nodes so workloads only run on agents |
| Control Plane vCPUs | `cp_vcpus` | integer | `4` | vCPUs per control-plane VM (minimum 2) |
| Control Plane Memory Size | `cp_memory_size` | string | `8GB` | Memory per control-plane VM |
| Control Plane OS Disk Size | `cp_os_disk_size` | string | `100GB` | OS disk size per control-plane VM |
| Control Plane Disk Controller | `cp_disk_controller` | string | `VIRTIO` | Disk controller: `VIRTIO`, `SATA`, or `SCSI` |

### Agent Node Profile Inputs

These inputs appear in the **Agent Node Profile** group and apply to all agent VMs.

| Display Label | Input | Type | Default | Description |
|---|---|---|---|---|
| Agent Node vCPUs | `ag_vcpus` | integer | `4` | vCPUs per agent VM (minimum 2) |
| Agent Node Memory Size | `ag_memory_size` | string | `8GB` | Memory per agent VM |
| Agent Node OS Disk Size | `ag_os_disk_size` | string | `100GB` | OS disk size per agent VM |
| Agent Node Disk Controller | `ag_disk_controller` | string | `VIRTIO` | Disk controller: `VIRTIO`, `SATA`, or `SCSI` |

### Per-Node Inputs

Each control-plane node (CP1, CP2, CP3) and agent node (AG1--AG6) has its own set of inputs for VM-specific configuration. The first control-plane node (CP1) inputs appear in the **First Control Plane Details** group; additional control-plane nodes appear in the **Additional Control Plane Details** group; agent nodes appear in the **Agent Node Details** group.

Common per-node inputs include:

| Display Label | Input Pattern | Type | Description |
|---|---|---|---|
| VM Name | `<prefix>_vm_name` / `<prefix>_name` | string | VM display name |
| Hostname | `<prefix>_hostname` | string | VM hostname (alphanumeric and hyphens, max 63 chars) |
| DataStore Path | `<prefix>_disk_wrapper` | string | Datastore path on the Endpoint (e.g. `/DataStore0`) |
| Virtual Network Segment | `<prefix>_vnic_0_segment_name` | string | Primary NIC virtual network segment |
| Use DHCP | `<prefix>_use_dhcp` | boolean | Use DHCP for the primary NIC |
| Static IP (CIDR) | `<prefix>_static_ip` | string | Static IP in CIDR notation (when DHCP is disabled) |
| Use Gateway | `<prefix>_use_gateway` | boolean | Configure a gateway (when DHCP is disabled) |
| Gateway IP | `<prefix>_gateway` | string | Gateway IP address |
| Use DNS | `<prefix>_use_dns` | boolean | Configure DNS servers (when DHCP is disabled) |
| DNS Servers | `<prefix>_dns` | list | DNS server IP addresses |
| Add Disks | `<prefix>_add_disks` | boolean | Add additional virtual disks |
| Additional Virtual Disks | `<prefix>_additional_disks` | list | Additional disk definitions |
| Add Network Interfaces | `<prefix>_add_nics` | boolean | Add additional network interfaces |
| Additional Network Interfaces | `<prefix>_vm_add_nics` | list | Additional NIC definitions |
| Enable Device Passthrough | `<prefix>_use_passthrough` | boolean | Enable device passthrough |
| USB Device List | `<prefix>_usb_wrapper` | list | USB device passthrough list |
| GPU Passthrough | `<prefix>_gpu_wrapper` | list | GPU passthrough list |
| PCIe Passthrough | `<prefix>_pcie_wrapper` | list | PCIe passthrough list |
| Video Passthrough | `<prefix>_video` | list | Video passthrough list |
| Serial Port | `<prefix>_serial_port_wrapper` | list | Serial port passthrough list |

> The `<prefix>` is `cp_1` for the first control plane, `cp_2`/`cp_3` for additional control planes, and `ag_1` through `ag_6` for agent nodes. Additional CP and AG nodes also include a `deployment_id` input that references an Endpoint service tag for placement.

### Deployment Scenarios

#### Single-Node Cluster

A single control-plane node with no agent nodes. The control-plane node runs all workloads (untainted by default).

- `number_of_control_plane` = `1`
- `number_of_agent_nodes` = `0`
- `control_plane_taint` = `false`

This is the simplest deployment and is suitable for development, testing, or resource-constrained edge environments.

#### Control-Plane Only (3 Nodes)

A highly available control-plane cluster with 3 nodes and no dedicated agent nodes. All 3 control-plane nodes participate in etcd quorum and can run workloads.

- `number_of_control_plane` = `3`
- `number_of_agent_nodes` = `0`
- `control_plane_taint` = `false`

This configuration provides etcd fault tolerance (tolerates 1 node failure) while keeping the cluster compact.

To taint the control-plane and prevent workloads from being scheduled on control-plane nodes, set `control_plane_taint` = `true`. Note that with 0 agent nodes and tainted control-plane nodes, no workloads will be schedulable.

#### Control-Plane with Agent Nodes

A production-grade cluster with dedicated control-plane and worker nodes. Control-plane nodes manage etcd and the Kubernetes API while agent nodes run application workloads.

- `number_of_control_plane` = `3`
- `number_of_agent_nodes` = `3` (or any value 1--6)
- `control_plane_taint` = `true` (recommended for workload separation)

This configuration is recommended for production environments where workload isolation from the control plane is desired.

### Multi-Node Deployment Outputs

After a successful deployment, the following capabilities are exposed:

| Output | Description |
|---|---|
| `rke2_api_url` | RKE2 API server URL (`https://<mgmt_ip>:6443`) |
| `rke2_join_token` | Cluster join token for adding nodes externally |
| `rke2_kubeconfig` | Path to the kubeconfig file on the CP1 node |
| `rke2_ca_cert` | Cluster CA certificate (PEM) |
| `rke2_ca_cert_b64` | Cluster CA certificate (base64-encoded) |
| `service_account` | DAP service account name |
| `bearer_token` | Bearer token for the DAP service account |
| `cluster_info` | Cluster summary (API URL, management IP, node counts) |
| `control_plane_nodes` | List of control-plane node details |
| `agent_nodes` | List of agent node details |
| `vm_user_name` | SSH username for all cluster VMs |
| `vm_ssh_private_key` | Secret name for the SSH private key |
| `dap_endpoint` | DAP infrastructure endpoint registration details |

### Multi-Node Technical Details

The multi-node blueprint is composed of several imported YAML files:

| File | Purpose |
|---|---|
| `multi-node/base_definitions.yaml` | Core node templates (SSH keys, binary image, base VM, env checks, installer) |
| `multi-node/deploy_inputs.yaml` | All deployment-level inputs (basic + advanced) |
| `multi-node/capabilities.yaml` | Deployment output capabilities |
| `multi-node/vm/profile_inputs.yaml` | Control-plane and agent VM hardware profiles |
| `multi-node/vm/scale_definitions.yaml` | Additional CP and AG node templates (scaling groups) |
| `multi-node/vm/cp_N_inputs.yaml` | Per-node inputs for control-plane nodes 1--3 |
| `multi-node/vm/ag_N_inputs.yaml` | Per-node inputs for agent nodes 1--6 |

**Plugins used:**

- `edge-plugin` (>=3.3.17.0) -- VM provisioning on NativeEdge
- `fabric-plugin` (>=3.4.2.0) -- SSH script execution via Python Fabric
- `utilities-plugin` (>=3.1.4.0) -- SSH key generation and utilities

---

## Standalone Deployment

**Blueprint:** `rke2_tech_ops.yaml`

### Standalone Overview

The standalone blueprint deploys RKE2 Kubernetes onto an existing edge-cloud-init VM deployment. It does not provision VMs; instead, it connects to a previously deployed VM via SSH using capabilities from the parent environment (e.g. `vm_name_id`, `vm_user_name`, `vm_ssh_private_key`).

This blueprint supports multiple operational tasks via the `run_arg` input, including fresh installation, Velero backup setup, monitoring stack installation, air-gapped archive creation, image pushing to a private registry, cluster joining, and uninstallation.

### Standalone Prerequisites

- An existing edge-cloud-init VM deployment in DAP that exposes the required capabilities (`vm_name_id`, `vm_user_name`, `vm_ssh_private_key`, `proxy_target_id`)
- The standalone blueprint must be deployed as a sub-environment or service of the parent VM deployment
- Network connectivity between the VM and the internet (or a configured offline archive / private registry)

### RKE2 Cluster Configuration Inputs

These inputs appear in the **RKE2 Cluster Configuration** group.

| Display Label | Input | Type | Default | Description |
|---|---|---|---|---|
| RKE2 Version | `rke2_version` | string | `v1.34.5+rke2r1` | RKE2 Kubernetes version to install |
| CNI Plugin | `cni_type` | string | `canal` | CNI plugin: `calico`, `canal`, `cilium`, or `none` |
| Enable CIS Hardening | `enable_cis` | boolean | `false` | Enable CIS Kubernetes hardening profile |
| Cluster CIDR | `cluster_cidr` | string | `10.42.0.0/16` | Pod network CIDR range |
| Service CIDR | `service_cidr` | string | `10.43.0.0/16` | Service network CIDR range |
| Max Pods Per Node | `max_pods` | integer | `110` | Maximum pods per node |
| Install NGINX Ingress | `install_ingress` | boolean | `true` | Install the RKE2 NGINX ingress controller |
| Install ServiceLB | `install_servicelb` | boolean | `true` | Install Klipper service load balancer |
| Install Local Path Provisioner | `install_local_path_provisioner` | boolean | `true` | Install Rancher local-path-provisioner storage class |
| Local Path Provisioner Version | `local_path_provisioner_version` | string | `v0.0.32` | Local-path-provisioner version |
| Install DNS Utility | `install_dns_utility` | boolean | `true` | Install Kubernetes DNS utility container |
| RKE2 Data Path | `rke2_data` | string | `default` | RKE2 data path (`default` = `/var/lib/rancher/rke2`) |
| Kubelet Data Path | `kubelet_data` | string | `default` | Kubelet data path (`default` = `/var/lib/kubelet`) |
| PVC Data Path | `pvc_data` | string | `default` | PVC storage path (`default` = `/opt/local-path-provisioner`) |
| Taint Control Plane | `control_plane_taint` | boolean | `false` | Taint the control-plane node for workload separation |
| TLS SAN | `tls_san` | string | `""` | Additional TLS SAN for the API server certificate |

### Velero Backup Configuration Inputs

These inputs appear in the **Velero Backup Configuration** group. Velero provides Kubernetes cluster backup and restore using an S3-compatible object store and CSI volume snapshots.

| Display Label | Input | Type | Default | Description |
|---|---|---|---|---|
| Velero Version | `velero_version` | string | `v1.17.1` | Velero CLI/server version |
| Velero AWS Plugin Version | `velero_aws_plugin_version` | string | `v1.13.0` | Velero AWS S3-compatible plugin version |
| Velero S3 Endpoint URL | `velero_s3_url` | string | `""` | S3 endpoint URL (e.g. `https://s3.example.com:8333`) |
| Velero S3 Access Key | `velero_s3_access_key` | string | `""` | S3 access key |
| Velero S3 Secret Key | `velero_s3_secret_key` | string | `""` | S3 secret key |
| Velero S3 Bucket | `velero_bucket` | string | `velero` | S3 bucket name |
| Velero Backup Namespaces | `velero_backup_namespaces` | string | `default` | Comma-separated namespaces to back up |
| Velero Backup Schedule | `velero_backup_schedule` | string | `0 2 * * *` | Cron schedule for daily backups |
| Velero Backup TTL | `velero_backup_ttl` | string | `720h` | Backup retention period |
| VolumeSnapshotClass Name | `vsc_name` | string | `longhorn-snapshot-vsc` | VolumeSnapshotClass name for CSI snapshots |
| VolumeSnapshotClass Driver | `vsc_driver` | string | `driver.longhorn.io` | CSI driver for VolumeSnapshotClass |
| Push/Save Velero Images | `push_save_velero` | boolean | `true` | Include Velero images in push/save operations |

### Monitoring Configuration Inputs

These inputs appear in the **Monitoring Configuration** group. The monitoring stack ships metrics and logs from the in-cluster Prometheus and Fluent Bit to an external monitoring host running Grafana, Loki, and Prometheus.

| Display Label | Input | Type | Default | Description |
|---|---|---|---|---|
| Monitoring Host | `monitoring_host` | string | `""` | IP or FQDN of the external monitoring host |
| Loki Port | `monitoring_loki_port` | integer | `3100` | Loki HTTP port on the monitoring host |
| Prometheus Port | `monitoring_prometheus_port` | integer | `9090` | Prometheus remote-write receiver port |
| Cluster Name | `cluster_name` | string | `edge-lab` | Label applied to metrics/logs for cluster identification |
| Kube Prometheus Stack Version | `kube_prometheus_stack_version` | string | `69.8.0` | kube-prometheus-stack Helm chart version |
| Fluent Bit Chart Version | `fluent_bit_chart_version` | string | `0.55.0` | Fluent Bit Helm chart version |
| Fluent Bit Version | `fluent_bit_version` | string | `4.2.2` | Fluent Bit application/image version |
| Helm Version | `helm_version` | string | `3.12.0` | Helm version to install if not present |
| Prometheus Retention | `prometheus_retention` | string | `48h` | In-cluster Prometheus data retention |
| Prometheus Storage Size | `prometheus_storage_size` | string | `50Gi` | PVC size for in-cluster Prometheus |
| Prometheus Storage Class | `prometheus_storage_class` | string | `longhorn` | StorageClass for Prometheus PVCs |
| Monitor Exclude Namespaces | `monitor_exclude_ns` | string | *(see default)* | Space-separated namespaces to skip during ServiceMonitor discovery |
| Monitor Port Names | `monitor_port_names` | string | *(see default)* | Space-separated port names treated as Prometheus metrics endpoints |
| Monitor Configs Directory | `monitor_configs_dir` | string | `""` | Optional directory of additional ServiceMonitor YAML files |
| Push/Save Monitoring Images | `push_save_monitoring` | boolean | `true` | Include monitoring images in push/save operations |

### Environment Configuration Inputs

These inputs appear in the **Environment Configuration** group.

| Display Label | Input | Type | Default | Description |
|---|---|---|---|---|
| Install Task | `run_arg` | string | `install` | Operation to perform (see [Install Tasks](#install-tasks)) |
| Join Mode | `join_mode` | string | `""` | Join type: `server` or `agent` (required for `join` task) |
| Join Server FQDN/IP | `join_server` | string | `""` | FQDN or IP of the RKE2 server to join |
| Join Token | `join_token` | string | `""` | Cluster join token from the RKE2 server |
| Script URL | `script_url` | string | *(GitHub URL)* | URL of the `rke2_installer.sh` script |
| Airgapped Mode | `offline_mode` | boolean | `false` | Enable air-gapped installation |
| Offline Binary Configuration Secret | `offline_binary_secret` | secret_key | -- | Offline archive secret (shown when offline mode is enabled) |
| Registry Authentication Secret | `registry_secret` | secret_key | -- | Registry authentication secret |
| Registry URL | `registry_url` | string | `""` | Private registry URL (e.g. `myregistry.lab:5000`) |
| Upload save package | `upload_package` | boolean | `false` | Upload the offline archive after creation (for `save` task) |
| Upload URL location | `upload_binary_secret` | secret_key | -- | Upload destination secret (shown when upload is enabled) |
| Log Output to hide | `hide_log_output` | list | `["stdout"]` | Log output to suppress: `stdout`, `stderr`, or `both` |
| Debug Logging | `debug` | integer | `1` | Debug logging (0 = off, 1 = on) |

### Install Tasks

The `run_arg` input controls which operation the standalone blueprint performs:

| Task | Description |
|---|---|
| `install` | Install RKE2 as a single-node server (untainted). Default task. |
| `install velero` | Install Velero backup into an existing RKE2 cluster. Requires S3 inputs. |
| `install monitoring` | Install kube-prometheus-stack and Fluent Bit. Requires `monitoring_host`. |
| `install push` | Install RKE2 and push all images to a private registry. Requires registry inputs. |
| `uninstall` | Fully uninstall RKE2 from the host. |
| `save` | Create an offline archive (`rke2-save.tar.gz`) for air-gapped use. |
| `push` | Push images to a private registry. Requires registry inputs. |
| `join` | Join an existing cluster. Requires `join_mode`, `join_server`, and `join_token`. |

### Standalone Deployment Outputs

After a successful deployment, the following capabilities are exposed:

| Output | Description |
|---|---|
| `rke2_service_running` | RKE2 service running status |
| `rke2_api_url` | RKE2 Kubernetes API server URL |
| `rke2_node_status` | Cluster node status |
| `rke2_join_token` | Cluster join token for adding nodes |
| `rke2_kubeconfig` | Path to the kubeconfig file |
| `offline_package_name` | Name of the offline archive (after `save` task) |
| `offline_package_uploaded` | Whether the offline archive was uploaded |
| `offline_package_url` | URL where the offline archive was uploaded |

### Standalone Technical Details

The standalone blueprint is composed of several imported YAML files:

| File | Purpose |
|---|---|
| `tech-ops/definitions.yaml` | Node templates (vm_info, env checks, installer) and DSL definitions |
| `tech-ops/inputs.yaml` | All inputs (RKE2 config, Velero, monitoring, environment) |
| `tech-ops/outputs.yaml` | Deployment output capabilities |

**Plugins used:**

- `edge-plugin` (>=3.3.17.0) -- NativeEdge integration
- `fabric-plugin` (>=3.4.2.0) -- SSH script execution via Python Fabric
- `utilities-plugin` (>=3.1.4.0) -- Utilities

---

## Input Examples

The DAP Orchestrator supports providing inputs as a YAML or JSON file. Below are example input files for common deployment scenarios.

### Multi-Node Examples

#### Single-Node Cluster (YAML)

```yaml
rke2_version: "v1.34.5+rke2r1"
number_of_control_plane: 1
number_of_agent_nodes: 0
edge_os_image_secret: my-os-image-secret
os_type: UBUNTU22.04
cp_1_vm_user_name: edgeuser
cp_1_vm_password: my-vm-password-secret
install_ingress: false
install_servicelb: false
install_local_path_provisioner: false
install_dns_utility: false
control_plane_taint: false
cp_vcpus: 4
cp_memory_size: 8GB
cp_os_disk_size: 100GB
cp_disk_controller: VIRTIO
cp_1_vm_name: rke2-cp-01
cp_1_hostname: rke2cp-01
cp_1_disk_wrapper: /DataStore0
cp_1_vnic_0_segment_name: my-bridge-segment
cp_1_use_dhcp: true
```

#### Single-Node Cluster (JSON)

```json
{
  "rke2_version": "v1.34.5+rke2r1",
  "number_of_control_plane": 1,
  "number_of_agent_nodes": 0,
  "edge_os_image_secret": "my-os-image-secret",
  "os_type": "UBUNTU22.04",
  "cp_1_vm_user_name": "edgeuser",
  "cp_1_vm_password": "my-vm-password-secret",
  "install_ingress": false,
  "install_servicelb": false,
  "install_local_path_provisioner": false,
  "install_dns_utility": false,
  "control_plane_taint": false,
  "cp_vcpus": 4,
  "cp_memory_size": "8GB",
  "cp_os_disk_size": "100GB",
  "cp_disk_controller": "VIRTIO",
  "cp_1_vm_name": "rke2-cp-01",
  "cp_1_hostname": "rke2cp-01",
  "cp_1_disk_wrapper": "/DataStore0",
  "cp_1_vnic_0_segment_name": "my-bridge-segment",
  "cp_1_use_dhcp": true
}
```

#### 3-Node HA Cluster with Agent Nodes (YAML)

```yaml
rke2_version: "v1.34.5+rke2r1"
number_of_control_plane: 3
number_of_agent_nodes: 3
edge_os_image_secret: my-os-image-secret
os_type: UBUNTU22.04
cp_1_vm_user_name: edgeuser
cp_1_vm_password: my-vm-password-secret

# Cluster options
install_ingress: true
install_servicelb: true
install_local_path_provisioner: true
local_path_provisioner_version: "v0.0.32"
install_dns_utility: true
cni_type: canal
control_plane_taint: true
tls_san: "rke2-cluster.lab.local"

# Control plane profile
cp_vcpus: 4
cp_memory_size: 16GB
cp_os_disk_size: 200GB
cp_disk_controller: VIRTIO

# Agent node profile
ag_vcpus: 8
ag_memory_size: 32GB
ag_os_disk_size: 200GB
ag_disk_controller: VIRTIO

# CP1 (base node)
cp_1_vm_name: rke2-cp-01
cp_1_hostname: rke2cp-01
cp_1_disk_wrapper: /DataStore0
cp_1_vnic_0_segment_name: my-bridge-segment
cp_1_use_dhcp: false
cp_1_static_ip: "192.168.1.101/24"
cp_1_use_gateway: true
cp_1_gateway: "192.168.1.1"
cp_1_use_dns: true
cp_1_dns:
  - "8.8.8.8"
  - "8.8.4.4"

# CP2
cp_2_name: rke2-cp-02
cp_2_hostname: rke2cp-02
cp_2_disk_wrapper: /DataStore0
cp_2_vnic_0_segment_name: my-bridge-segment
cp_2_use_dhcp: false
cp_2_static_ip: "192.168.1.102/24"
cp_2_use_gateway: true
cp_2_gateway: "192.168.1.1"
cp_2_use_dns: true
cp_2_dns:
  - "8.8.8.8"
  - "8.8.4.4"

# CP3
cp_3_name: rke2-cp-03
cp_3_hostname: rke2cp-03
cp_3_disk_wrapper: /DataStore0
cp_3_vnic_0_segment_name: my-bridge-segment
cp_3_use_dhcp: false
cp_3_static_ip: "192.168.1.103/24"
cp_3_use_gateway: true
cp_3_gateway: "192.168.1.1"
cp_3_use_dns: true
cp_3_dns:
  - "8.8.8.8"
  - "8.8.4.4"

# AG1
ag_1_name: rke2-ag-01
ag_1_hostname: rke2-ag-01
ag_1_disk_wrapper: /DataStore0
ag_1_vnic_0_segment_name: my-bridge-segment
ag_1_use_dhcp: false
ag_1_static_ip: "192.168.1.111/24"
ag_1_use_gateway: true
ag_1_gateway: "192.168.1.1"
ag_1_use_dns: true
ag_1_dns:
  - "8.8.8.8"

# AG2
ag_2_name: rke2-ag-02
ag_2_hostname: rke2-ag-02
ag_2_disk_wrapper: /DataStore0
ag_2_vnic_0_segment_name: my-bridge-segment
ag_2_use_dhcp: false
ag_2_static_ip: "192.168.1.112/24"
ag_2_use_gateway: true
ag_2_gateway: "192.168.1.1"
ag_2_use_dns: true
ag_2_dns:
  - "8.8.8.8"

# AG3
ag_3_name: rke2-ag-03
ag_3_hostname: rke2-ag-03
ag_3_disk_wrapper: /DataStore0
ag_3_vnic_0_segment_name: my-bridge-segment
ag_3_use_dhcp: false
ag_3_static_ip: "192.168.1.113/24"
ag_3_use_gateway: true
ag_3_gateway: "192.168.1.1"
ag_3_use_dns: true
ag_3_dns:
  - "8.8.8.8"
```

#### Multi-Node with Private Registry (YAML)

```yaml
rke2_version: "v1.34.5+rke2r1"
number_of_control_plane: 1
number_of_agent_nodes: 0
edge_os_image_secret: my-os-image-secret
os_type: UBUNTU22.04
cp_1_vm_user_name: edgeuser
cp_1_vm_password: my-vm-password-secret
install_ingress: false
install_servicelb: false
install_local_path_provisioner: false
install_dns_utility: false
control_plane_taint: false

# Private registry
use_registry: true
registry_secret: my-registry-auth-secret
registry_url: "myregistry.lab:5000"
push_images: true

# Node config
cp_vcpus: 4
cp_memory_size: 8GB
cp_os_disk_size: 100GB
cp_1_vm_name: rke2-cp-01
cp_1_hostname: rke2cp-01
cp_1_disk_wrapper: /DataStore0
cp_1_vnic_0_segment_name: my-bridge-segment
cp_1_use_dhcp: true
```

#### Multi-Node with DAP Infrastructure Registration (YAML)

```yaml
rke2_version: "v1.34.5+rke2r1"
number_of_control_plane: 1
number_of_agent_nodes: 0
edge_os_image_secret: my-os-image-secret
os_type: UBUNTU22.04
cp_1_vm_user_name: edgeuser
cp_1_vm_password: my-vm-password-secret
install_ingress: false
install_servicelb: false
install_local_path_provisioner: false
install_dns_utility: false
control_plane_taint: false

# DAP registration
register_dap_infrastructure: true
dap_endpoint_name: "my-edge-rke2-cluster"

# Node config
cp_vcpus: 4
cp_memory_size: 8GB
cp_os_disk_size: 100GB
cp_1_vm_name: rke2-cp-01
cp_1_hostname: rke2cp-01
cp_1_disk_wrapper: /DataStore0
cp_1_vnic_0_segment_name: my-bridge-segment
cp_1_use_dhcp: true
```

### Standalone Examples

#### Basic Install (YAML)

```yaml
rke2_version: "v1.34.5+rke2r1"
cni_type: canal
run_arg: install
install_ingress: true
install_servicelb: true
install_local_path_provisioner: true
install_dns_utility: true
debug: 1
```

#### Basic Install (JSON)

```json
{
  "rke2_version": "v1.34.5+rke2r1",
  "cni_type": "canal",
  "run_arg": "install",
  "install_ingress": true,
  "install_servicelb": true,
  "install_local_path_provisioner": true,
  "install_dns_utility": true,
  "debug": 1
}
```

#### Install with Velero Backup (YAML)

```yaml
rke2_version: "v1.34.5+rke2r1"
cni_type: canal
run_arg: "install velero"
install_ingress: true
install_servicelb: true
install_local_path_provisioner: true
install_dns_utility: true

# Velero S3 configuration
velero_version: "v1.17.1"
velero_aws_plugin_version: "v1.13.0"
velero_s3_url: "https://s3.example.com:8333"
velero_s3_access_key: "my-access-key"
velero_s3_secret_key: "my-secret-key"
velero_bucket: "velero"
velero_backup_namespaces: "default,my-app"
velero_backup_schedule: "0 2 * * *"
velero_backup_ttl: "720h"
```

#### Install with Monitoring Stack (YAML)

```yaml
rke2_version: "v1.34.5+rke2r1"
cni_type: canal
run_arg: "install monitoring"
install_ingress: true
install_servicelb: true
install_local_path_provisioner: true
install_dns_utility: true

# Monitoring configuration
monitoring_host: "192.168.1.50"
monitoring_loki_port: 3100
monitoring_prometheus_port: 9090
cluster_name: "edge-prod-01"
```

#### Join as Agent Node (YAML)

```yaml
run_arg: join
join_mode: agent
join_server: "192.168.1.101"
join_token: "K10abc123::server:xyz789"
```

#### Join as Additional Server Node (YAML)

```yaml
run_arg: join
join_mode: server
join_server: "192.168.1.101"
join_token: "K10abc123::server:xyz789"
tls_san: "rke2-cluster.lab.local"
control_plane_taint: true
```

#### Air-Gapped Install (YAML)

```yaml
rke2_version: "v1.34.5+rke2r1"
cni_type: canal
run_arg: install
offline_mode: true
offline_binary_secret: my-offline-archive-secret
install_ingress: true
install_servicelb: true
install_local_path_provisioner: true
install_dns_utility: true
```

#### Create Offline Archive (YAML)

```yaml
run_arg: save
upload_package: true
upload_binary_secret: my-upload-destination-secret
```

---

## References

| Resource | URL |
|---|---|
| RKE2 -- Rancher's Next-Generation Kubernetes Distribution | [https://docs.rke2.io](https://docs.rke2.io) |
| rke2_installer.sh -- RKE2 Installer Script | [https://github.com/Chubtoad5/rke2-installer](https://github.com/Chubtoad5/rke2-installer) |
| Python Fabric -- SSH Remote Execution | [https://www.fabfile.org](https://www.fabfile.org) |
| Dell Technologies | [https://www.dell.com](https://www.dell.com) |
| Dell NativeEdge Documentation | [https://www.dell.com/support/home/en-us/product-support/product/dell-nativeedge/overview](https://www.dell.com/support/home/en-us/product-support/product/dell-nativeedge/overview) |
| Velero -- Kubernetes Backup and Restore | [https://velero.io](https://velero.io) |
| Prometheus -- Monitoring and Alerting | [https://prometheus.io](https://prometheus.io) |
| Grafana -- Observability Dashboards | [https://grafana.com/oss/grafana](https://grafana.com/oss/grafana) |
| Grafana Loki -- Log Aggregation | [https://grafana.com/oss/loki](https://grafana.com/oss/loki) |
| Fluent Bit -- Log Processor and Forwarder | [https://fluentbit.io](https://fluentbit.io) |
| kube-prometheus-stack -- Helm Chart | [https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack) |
| Helm -- Kubernetes Package Manager | [https://helm.sh](https://helm.sh) |
| Rancher Local Path Provisioner | [https://github.com/rancher/local-path-provisioner](https://github.com/rancher/local-path-provisioner) |
| Kubernetes CIS Benchmark | [https://www.cisecurity.org/benchmark/kubernetes](https://www.cisecurity.org/benchmark/kubernetes) |
