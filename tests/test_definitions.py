"""The blueprint YAML: how the install nodes run, and what the inputs accept.

    python3 -m unittest discover -s tests
"""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def nodes(path):
    return yaml.safe_load((ROOT / path).read_text())["node_templates"]


def inputs(path):
    return yaml.safe_load((ROOT / path).read_text())["inputs"]


def op(node, name):
    return node["interfaces"]["dell.interfaces.lifecycle"][name]


def process(operation):
    return (operation["inputs"].get("process") or {}).get("env") or {}


def quoted(value):
    """A text value the fabric plugin exports unquoted must be wrapped in single quotes."""
    return isinstance(value, dict) and "concat" in value and value["concat"][0] == "'" and value["concat"][-1] == "'"


STANDALONE = "tech-ops/definitions.yaml"
BASE = "multi-node/base_definitions.yaml"
SCALE = "multi-node/vm/scale_definitions.yaml"
# Booleans, numbers and fixed words, which need no quotes.
UNQUOTED = {"OFFLINE_MODE", "ENABLE_CIS", "MAX_PODS", "INSTALL_INGRESS", "INSTALL_SERVICELB",
            "INSTALL_LOCAL_PATH_PROVISIONER", "INSTALL_DNS_UTILITY", "CONTROL_PLANE_TAINT", "DEBUG",
            "RKE2_FORCE_ONLINE", "PUSH_SAVE_VELERO", "PUSH_SAVE_MONITORING", "MONITORING_LOKI_PORT",
            "MONITORING_PROMETHEUS_PORT", "UPLOAD_OFFLINE_PACKAGE", "ROLE", "PUSH_IMAGES"}

SCRIPT_NODES = [
    (STANDALONE, "env_precheck", "create"), (STANDALONE, "install_app", "create"),
    (STANDALONE, "install_app", "stop"), (STANDALONE, "env_postcheck", "create"),
    (BASE, "env_precheck", "create"), (BASE, "install_app", "create"), (BASE, "install_app", "stop"),
    (BASE, "env_postcheck", "create"),
    (SCALE, "cp_env_precheck", "create"), (SCALE, "install_cp", "create"), (SCALE, "install_cp", "stop"),
    (SCALE, "cp_env_postcheck", "create"), (SCALE, "ag_env_precheck", "create"),
    (SCALE, "install_ag", "create"), (SCALE, "install_ag", "stop"), (SCALE, "ag_env_postcheck", "create"),
]


class DefinitionsTests(unittest.TestCase):
    def test_scripts_exist_and_values_quoted(self):
        for path, node, name in SCRIPT_NODES:
            with self.subTest(node=node, op=name, file=path):
                operation = op(nodes(path)[node], name)
                self.assertEqual(operation["implementation"], "fabric.fabric_plugin.tasks.run_script")
                self.assertTrue((ROOT / operation["inputs"]["script_path"]).is_file())
                for key, value in process(operation).items():
                    if key not in UNQUOTED:
                        self.assertTrue(quoted(value), f"{key} isn't single-quoted")

    def test_no_retries(self):
        for path, node, name in SCRIPT_NODES:
            if name == "stop":
                continue
            with self.subTest(node=node, file=path):
                self.assertEqual(op(nodes(path)[node], name)["inputs"].get("non_recoverable_error_exit_codes"), [1])

    def test_roles(self):
        self.assertEqual(process(op(nodes(BASE)["install_app"], "create"))["ROLE"], "cp1")
        self.assertEqual(process(op(nodes(SCALE)["install_cp"], "create"))["ROLE"], "cp")
        self.assertEqual(process(op(nodes(SCALE)["install_ag"], "create"))["ROLE"], "agent")

    def test_secrets_only_where_used(self):
        """The prechecks no longer see the join token or the registry password."""
        for path, node in [(STANDALONE, "env_precheck"), (BASE, "env_precheck"), (SCALE, "cp_env_precheck"),
                           (SCALE, "ag_env_precheck")]:
            names = set(process(op(nodes(path)[node], "create")))
            self.assertFalse(names & {"REG_PASS", "JOIN_TOKEN"}, node)
        for path, node in [(SCALE, "install_cp"), (SCALE, "install_ag")]:
            self.assertIn("JOIN_TOKEN", process(op(nodes(path)[node], "create")))

    def test_stop_gets_the_data_paths(self):
        for path, node in [(STANDALONE, "install_app"), (BASE, "install_app"), (SCALE, "install_cp"),
                           (SCALE, "install_ag")]:
            names = set(process(op(nodes(path)[node], "stop")))
            self.assertTrue({"RKE2_DATA", "KUBELET_DATA", "PVC_DATA", "INSTALL_LOCAL_PATH_PROVISIONER"} <= names)

    def test_postchecks_sudo(self):
        # Standalone runs as the VM user, so ~ is where the installer left the save package.
        self.assertFalse(op(nodes(STANDALONE)["env_postcheck"], "create")["inputs"].get("use_sudo", False))


PIN = "https://github.com/Chubtoad5/rke2-installer/releases/download/v1.3.1/rke2_installer.sh"

GOOD = {
    "rke2_version": ["v1.34.5+rke2r1", "v1.33.13+rke2r2"],
    "cluster_cidr": ["10.42.0.0/16", "10.42.0.0/16,2001:cafe:42::/56"],
    "rke2_data": ["default", "/opt/rke2", "/data/rke2-data_1"],
    "tls_san": ["", "rke2.example.com", "192.168.1.50"],
    "join_server": ["", "rke2.example.com", "10.0.0.5"],
    "join_token": ["", "K10abc::server:def"],
    "cluster_name": ["", "edge-lab", "Edge.Lab_2"],
    "velero_backup_namespaces": ["", "default", "default,apps"],
    "velero_backup_schedule": ["", "0 2 * * *", "@daily", "0 */6 * * MON-FRI"],
    "velero_backup_ttl": ["720h", "720h0m0s"],
    "monitor_exclude_ns": ["kube-system kube-public default"],
    "prometheus_storage_size": ["50Gi", "1.5Ti"],
    "helm_version": ["", "4.0.1", "v3.12.0"],
    "script_url": [PIN, "https://example.com/x/rke2_installer.sh"],
}
BAD = {
    "rke2_version": ["1.34.5", "v1.34.5", "v1.34.5+rke2r1'"],
    "cluster_cidr": ["10.42.0.0", "10.42.0.0/16 ", "a'b/16"],
    "rke2_data": ["relative/path", "/opt/rke 2", "/opt/'x", ""],
    "tls_san": ["https://rke2.example.com", "Rke2.Example.com", "rke2", "a'b.com"],
    "join_server": ["rke2:6443", "x'y.com"],
    "join_token": ["K10 abc", "K10'abc"],
    "cluster_name": ["Edge Lab", "edge'lab", "-edge"],
    "velero_backup_namespaces": ["*", "default apps", "a'b"],
    "velero_backup_schedule": ["0 2 * * *'", "0  2 * * *", "$(id)"],
    "monitor_exclude_ns": ["kube-system  default", "a*b"],
    "helm_version": ["4.0 .1", "'4'"],
    "script_url": ["https://example.com/x/install.sh", "https://example.com/x'y/rke2_installer.sh",
                   "https://example.com/$x/rke2_installer.sh"],
}


class InputPatternTests(unittest.TestCase):
    def pattern(self, path, name):
        for c in inputs(path)[name].get("constraints") or []:
            if "pattern" in c:
                return c["pattern"]
        self.fail(f"{name} has no pattern")

    def test_good_and_bad(self):
        for path in ("tech-ops/inputs.yaml", "multi-node/deploy_inputs.yaml"):
            defined = inputs(path)
            for name, values in GOOD.items():
                if name not in defined:
                    continue
                for v in values:
                    with self.subTest(file=path, input=name, value=v):
                        self.assertTrue(re.search(self.pattern(path, name), v))
            for name, values in BAD.items():
                if name not in defined:
                    continue
                for v in values:
                    with self.subTest(file=path, input=name, value=v):
                        self.assertFalse(re.search(self.pattern(path, name), v))

    def test_every_text_input_refuses_a_single_quote(self):
        for path in ("tech-ops/inputs.yaml", "multi-node/deploy_inputs.yaml"):
            for name, spec in inputs(path).items():
                if spec.get("type") != "string" or spec.get("hidden") or "valid_values" in str(spec.get("constraints")):
                    continue
                # Not for a shell: fabric's SSH user, and the VM component's blueprint.
                if name in ("cp_1_vm_user_name", "utility_blueprint_id", "utility_blueprint_revision"):
                    continue
                with self.subTest(file=path, input=name):
                    pat = self.pattern(path, name)
                    self.assertFalse(re.search(pat, "a'b"), pat)

    def test_defaults_match(self):
        for path in ("tech-ops/inputs.yaml", "multi-node/deploy_inputs.yaml"):
            for name, spec in inputs(path).items():
                default = spec.get("default")
                for c in spec.get("constraints") or []:
                    if "pattern" in c and isinstance(default, str):
                        with self.subTest(file=path, input=name):
                            self.assertTrue(re.search(c["pattern"], default))

    def test_pin(self):
        for path in ("tech-ops/inputs.yaml", "multi-node/deploy_inputs.yaml"):
            self.assertEqual(inputs(path)["script_url"]["default"], PIN)


if __name__ == "__main__":
    unittest.main()
