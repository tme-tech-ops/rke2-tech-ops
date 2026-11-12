# Changelog for rke2-tech-ops

All notable changes to these blueprints are recorded here. The version is also
the catalog revision to upload each entry point as (see the README): the
multi-node blueprint (`rke2_tech_ops_multi-node.yaml`) and the standalone
blueprint (`rke2_tech_ops.yaml`) share it.

## 1.2.1.0 - unreleased

Moves to rke2-installer `v1.3.1` and fixes what was wrong in 1.2.0.0, in both
entry points. Updating a 1.2.0.0 deployment to it changes nothing on the VMs.

### Both

- Changed: `script_url` defaults to the installer's `v1.3.1` release asset
  instead of commit `0e066ba`. The prechecks check a GitHub release asset
  against that release's `SHA256SUMS`, keep a file that doesn't match off the
  VM, and no longer download with `curl -k`. A failed download says why (under
  `set -e` the multi-node checks after `curl` and `tar` never ran). In
  airgapped mode the offline package is downloaded and extracted on every
  install, so a new package with the same name replaces the old one.
- Changed: the installer runs through the fabric plugin's `run_script` instead
  of `run_commands`. The prechecks assembled a command string with the join
  token and the registry password in it, stored it in a runtime property
  (`install_cmd`), and `run_commands` wrote it to the event log. A new
  `rke2_app.sh` passes each argument whole, and nothing stores or logs them.
- Fixed: text values reached the installer through an unquoted shell `export`,
  so `$`, backticks, `\`, `*` and spaces in a password or other value were
  changed or broke the command (a cluster name `Edge Lab` was split). They are
  now single-quoted, and every text input is validated: the RKE2 version, the
  CIDRs, the data paths (absolute or `default`), TLS SAN and Join Server
  (lowercase FQDN or IPv4), the cluster name and the rest. None accepts a
  single quote, and the README says the secrets' values can't hold one.
- Fixed: the scripts left their settings, passwords and the join token
  included, in env files on the VMs. Each script now deletes its env file
  first.
- Fixed: a failed check or install was retried for a long time, re-running the
  installer each time. They now fail at once (exit code 1).
- Fixed: the postchecks published a result without checking it. They now fail
  when the RKE2 service isn't active after a task that installs RKE2, and
  report `NotReady`, which CNI `none` leaves until a CNI is installed.
- Fixed: `stop` didn't pass the data paths, so an uninstall left custom
  `rke2_data`, `kubelet_data` and `pvc_data` directories behind. It now passes
  them, and installer `v1.3.1` removes them.
- Changed: a registry password with a double quote, a backslash, a space or
  tab, `*`, `?` or `[` stops the install before the installer runs, with the
  reason. Installer `v1.3.1` writes the password into `registries.yaml`
  unescaped and passes it to its image push unquoted, so it would change them.
  The password comes from a secret, so the form can't refuse it.
- Changed: online installs set `RKE2_FORCE_ONLINE=true`, so an
  `rke2-save-version.txt` left by an earlier `save` can't switch them to
  air-gapped mode.
- Fixed: texts. The `debug` description was inverted (standalone). The README
  now names the installer each version runs, says that airgapped mode runs the
  package's installer, that a server with the ingress needs `iptables`, that CNI
  `none` leaves the nodes `NotReady`, and that a Heal of an install node needs
  Force reinstall.

### Multi-node

- Fixed: CP2-3 and the agents could join with token `N/A`. CP1's postcheck read
  the token from `/var/lib/rancher/rke2` whatever `rke2_data` was, and the join
  checks refused only an empty token. The postcheck now reads it from the
  cluster's data path and fails without one, and a joining node accepts only a
  node-token (`K10…`). The postchecks also find `kubectl` under a custom
  `rke2_data`.
- Changed: agents no longer get the settings only servers read (CIDRs,
  ServiceLB, local-path, DNS utility, taint, PVC path), so their installer
  doesn't warn that it ignores them.
- Changed: the three prechecks are one script, `multi-node/scripts/env_precheck.sh`,
  which only puts the installer on the VM.

### Standalone

- Fixed: with Registry URL set, `uninstall` and `save` failed, and with TLS SAN
  set, `push` failed: the installer refuses those flags with them. `-registry`
  now goes only to `install`, `install push`, `push` and `join`, `-tls-san` only
  to `install`, `install push` and `join` as a server, and `push` or
  `install push` without a registry stops with a reason.
- Fixed: a reinstall or Heal of an `uninstall` task deployment ran `uninstall`
  again. The task now runs only when the deployment is installed.
- Fixed: the join token was published from `/var/lib/rancher/rke2` whatever
  `rke2_data` was.
- Fixed: `env_postcheck` ran as root, so it looked for a `save` package in
  root's home directory instead of the one the installer wrote to. It now runs
  as the VM user, with `sudo` only for what needs root.
- Lint: the remaining findings are the plain-text `join_token` and Velero keys,
  left for the credentials change. The linter no longer flags their uses,
  because they are wrapped in quotes.

## 1.2.0.0 - 2026-10-31

Safe deployment updates (Day-2). The multi-node blueprint needs
`edge-cloudinit-utility-vm` 1.2.0.0 or a later 1.x revision.

### Multi-node

- Fixed: an update could uninstall RKE2. Each install node's `stop` ran the
  installer's `uninstall`, and an update's automatic reinstall, a reinstall
  list or Heal runs `stop`. RKE2 and its data are now removed only when the
  deployment is uninstalled (or a node is scaled away); in other workflows
  `stop` keeps them.
- Changed: an update never re-runs the installer. The install, precheck and
  postcheck nodes report no drift and have no update operation, so a
  no-change update or a move to a new revision of this blueprint doesn't
  touch the cluster. RKE2 settings are fixed at install.
- Added: `utility_blueprint_revision` (default 1.2.0.0) pins the utility
  blueprint revision the VMs use. Before, every update moved the VMs to the
  newest utility revision in the catalog.
- Fixed: CP2-3 and the agents kept their install-time sizes. Agents now take
  vCPUs, memory and OS disk from the Agent Node Profile on every update, and
  their additional disks from their own inputs (picked by VM name). CP1's
  disks can change too (CP2-3's stay fixed, so one control plane restarts at a
  time), and with one control plane its profile.
- Added: `update_checks` refuses, with the reason and with the VMs left as
  they are, an update that would shrink a disk, or a Control Plane Profile
  change when the cluster has more than one control plane (the control planes
  keep their install-time sizes: restarting them together would lose etcd
  quorum). With one control plane the change applies; the Kubernetes API is
  down while the VM restarts. On a 3-CP cluster created before 1.2, CP1 has no
  install-time record and follows the profile alone (one restart, quorum
  kept). It also warns at the start of an update when an app deployed on a VM
  will block it.
- Fixed: an update with no change still updated VM deployments. The first
  control plane's hidden list inputs (passthrough, additional disks) reached it
  as null, and CP2-3 and the agents didn't send `iso_files` and `boot_order`;
  the component compares what it sends with all of the VM deployment's inputs.
  Every input is now sent with an explicit value.
- Fixed: the cloud-init password hash changed on every run of `prep_config`
  (new random salt). The salt is now derived from the deployment ID.
- Fixed: `cluster_info`, `control_plane_nodes` and `agent_nodes` are read from
  the VM deployments again after an update.
- Fixed: Push Images to Registry did nothing; it now adds `push` to the
  first control plane's install command.
- Fixed: the agents' NAT port forwarding inputs were never used; they now
  apply at install.
- Fixed: the install command was logged with the registry password and the
  join token; both are masked now.
- Changed: `script_url` defaults to a pinned installer commit instead of the
  installer's `main` branch, so a new installer commit can't change a
  deployment. Only VM sizes, additional disks and the utility revision are
  updatable; everything else is locked (see "Updating a multi-node
  deployment" in the README).
- Changed: plugin imports moved to the entry file; every input constraint has
  an error message; list inputs declare their item type; `max_pods` and
  `debug` are validated; the `solution` and `version` labels are corrected.
  Lint: 0 errors and 0 warnings apart from the 8 Endpoint pickers of CP2-3
  and the agents (`input-no-deployment-type`), which stay `deployment_id`
  inputs on purpose.

### Standalone

- Fixed: uninstalling any standalone deployment ran the installer's
  `uninstall`, so removing a Velero, monitoring, save or push deployment wiped
  the cluster it worked on, and an update's reinstall or Heal of
  `install_app` did the same. `stop` now uninstalls RKE2 only when the
  deployment is uninstalled and its Install Task installed RKE2 (`install`,
  `install push`, `join`).
- Changed: an update never re-runs the task. `env_precheck`, `install_app`
  and `env_postcheck` report no drift and have no update operation. Every
  input is locked: a task's settings are fixed at install (see "Updating a
  Standalone Deployment" in the README).
- Changed: `script_url` defaults to the pinned installer commit.
- Fixed: the install command was logged with the join token and the registry
  password, and the offline download with its password; both are masked or
  gone.
- Changed: plugin imports moved to the entry file (fabric only; edge and
  utilities were unused); unused hidden inputs removed; every constraint has
  an error message; `max_pods`, `debug` and the monitoring ports are
  validated; the version label is corrected. Lint: the remaining findings are
  the plain-text join token and Velero S3 keys, left for the credentials
  change (secret inputs) that follows this release.

## 1.1.5.0

Release restructure and pinning supported plugins for DAP 2.0.0.1 / DDPC 4.2.0.0 -
untested (2026-11-01).

- On branch `ddpc-4.2.0.0-snapshot`, not on `main`: the 1.2.0.0 code for DAP
  2.0.0.1 with DDPC 4.2.0.0, not tested on that platform.
- Multi-node: edge-plugin pinned to 3.3.25.0 and utilities-plugin to 3.1.4.0 (the
  versions DAP 2.0.0.1 ships); `utility_blueprint_revision` defaults to 1.1.5.0, the
  edge-cloudinit-utility-vm snapshot for that platform (same input and capability
  names as 1.2.0.0). Standalone: imports only the fabric-plugin, unchanged.
- Tags are now blueprint versions. Each has a GitHub release named after the DAP
  and DDPC versions it was tested on, with upload-ready zips.

## 1.0.3 and earlier

Catalog revisions 1.0.0-1.0.3 (multi-node) and 1.0.0 (standalone), before
this changelog.
