import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "multi-node/scripts/update_checks.py"


def load(names):
    """The named functions and constants from update_checks.py, without its dell imports."""
    tree = ast.parse(SCRIPT.read_text())
    body = ast.parse("import re").body
    body += [node for node in tree.body
             if (isinstance(node, ast.FunctionDef) and node.name in names)
             or (isinstance(node, ast.Assign)
                 and any(getattr(t, "id", None) in ("UNITS", "END_STATES") for t in node.targets))]
    namespace = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), SCRIPT, "exec"), namespace)
    return namespace


GB = 2**30
FNS = load(["to_bytes", "disk_sizes", "shrinks", "profile_changes"])


def applied(cpu=4, memory=8 * GB, storage=40 * GB, disks=()):
    return {"resource_constraints": {"cpu": cpu, "memory": memory, "storage": storage},
            "additional_disks": [{"name": n, "disk": "/DataStore0", "storage": s * GB} for n, s in disks]}


class ProfileChangesTests(unittest.TestCase):
    profile_changes = staticmethod(FNS["profile_changes"])
    profile = {"vcpus": 4, "memory": "8GB", "storage": "40GB"}

    def test_same_sizes(self):
        self.assertEqual(self.profile_changes(self.profile, ["cp1", "cp2"],
                                              {"cp1": applied(), "cp2": applied()}), [])

    def test_vcpus_changed(self):
        found = self.profile_changes(dict(self.profile, vcpus=6), ["cp1", "cp2"],
                                     {"cp1": applied(), "cp2": applied()})
        self.assertEqual(found, ["cp1 (vCPUs)", "cp2 (vCPUs)"])

    def test_memory_and_disk_changed(self):
        found = self.profile_changes(dict(self.profile, memory="16GB", storage="60GB"), ["cp1"],
                                     {"cp1": applied()})
        self.assertEqual(found, ["cp1 (memory, OS disk)"])

    def test_agents_are_not_checked(self):
        found = self.profile_changes(dict(self.profile, vcpus=6), ["cp1"],
                                     {"cp1": applied(), "ag1": applied(cpu=2)})
        self.assertEqual(found, ["cp1 (vCPUs)"])

    def test_vm_without_record_is_skipped(self):
        self.assertEqual(self.profile_changes(dict(self.profile, vcpus=6), ["cp1"], {}), [])


class ShrinksTests(unittest.TestCase):
    shrinks = staticmethod(FNS["shrinks"])

    def test_grow_is_fine(self):
        requested = {"ag1": {"name": "ag1", "storage": "50GB", "add_disks": True,
                             "disks": [{"name": "d1", "storage": 20, "storage_unit": "GB"}]}}
        self.assertEqual(self.shrinks(requested, {"ag1": applied(disks=[("d1", 10)])}), [])

    def test_os_disk_shrink(self):
        requested = {"ag1": {"name": "ag1", "storage": "30GB"}}
        self.assertEqual(self.shrinks(requested, {"ag1": applied()}), ["ag1: OS disk 40GB -> 30GB"])

    def test_additional_disk_shrink(self):
        requested = {"cp1": {"name": "cp1", "storage": "40GB", "add_disks": True,
                             "disks": [{"name": "d1", "storage": 5}]}}
        self.assertEqual(self.shrinks(requested, {"cp1": applied(disks=[("d1", 10)])}),
                         ["cp1: disk d1 10GB -> 5GB"])

    def test_removed_disk_is_not_a_shrink(self):
        requested = {"cp1": {"name": "cp1", "storage": "40GB", "add_disks": False, "disks": None}}
        self.assertEqual(self.shrinks(requested, {"cp1": applied(disks=[("d1", 10)])}), [])

    def test_vm_not_requested_is_skipped(self):
        self.assertEqual(self.shrinks({}, {"cp1": applied()}), [])


if __name__ == "__main__":
    unittest.main()
