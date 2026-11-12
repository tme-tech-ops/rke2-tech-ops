"""The VM-side scripts, run under dash and bash with stand-ins for ctx, sudo, curl, systemctl and the installer.

    python3 -m unittest discover -s tests
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELLS = [s for s in ("dash", "bash") if shutil.which(s)]

STUBS = {
    # ctx: log lines and runtime properties go to files; workflow-id from the test.
    "ctx": r'''#!/bin/sh
case "$1" in
  logger) shift; printf '%s %s\n' "$1" "$2" >> "$STUB_DIR/log" ;;
  workflow-id) printf '%s\n' "${CTX_WORKFLOW:-install}" ;;
  instance) printf '%s=%s\n' "$3" "$4" >> "$STUB_DIR/props" ;;
esac
''',
    "sudo": '#!/bin/sh\n[ "$1" = "-E" ] && shift\nexec "$@"\n',
    "hostname": '#!/bin/sh\necho 10.0.0.5\n',
    # systemctl is-active --quiet <unit>: active when the unit is in $ACTIVE
    "systemctl": '#!/bin/sh\nfor u in $ACTIVE; do [ "$u" = "$3" ] && exit 0; done\nexit 3\n',
    # curl <flags> URL -o file: serves $STUB_DIR/www/<basename of URL>; fails for a missing file
    "curl": r'''#!/bin/sh
out=""; url=""
while [ $# -gt 0 ]; do
  case "$1" in -o) out="$2"; shift 2 ;; -u|--retry) shift 2 ;; http*) url="$1"; shift ;; *) shift ;; esac
done
f="$STUB_DIR/www/$(basename "$url")"
[ -f "$f" ] || exit 22
if [ -n "$out" ]; then cp "$f" "$out"; else cat "$f"; fi
''',
}

# The fake installer records each argument on its own line, and some settings.
FAKE_INSTALLER = r'''#!/bin/sh
SCRIPT_VERSION="1.3.1"
: > "$STUB_DIR/args"
for a in "$@"; do printf '%s\n' "$a" >> "$STUB_DIR/args"; done
for n in RKE2_VERSION CLUSTER_CIDR PVC_DATA RKE2_DATA REG_PASS JOIN_TOKEN TLS_SAN RKE2_FORCE_ONLINE CLUSTER_NAME; do
  eval "v=\${$n-<unset>}"; printf '%s=%s\n' "$n" "$v" >> "$STUB_DIR/seen"
done
exit "${FAKE_RC:-0}"
'''


class Bed:
    """A temporary HOME and stub PATH. run() executes a script under a shell with exported settings."""

    def __init__(self):
        self.dir = Path(tempfile.mkdtemp())
        self.home = self.dir / "home"
        self.bin = self.dir / "bin"
        self.www = self.dir / "www"
        for d in (self.home, self.bin, self.www):
            d.mkdir()
        for name, body in STUBS.items():
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        (self.home / "rke2_installer.sh").write_text(FAKE_INSTALLER)
        (self.home / "rke2_installer.sh").chmod(0o755)

    def run(self, shell, script, settings, workflow="install", active=""):
        # Like the fabric plugin: the script sits beside env-<script>, which it must delete.
        workdir = self.dir / "scripts"
        workdir.mkdir(exist_ok=True)
        copy = workdir / Path(script).name
        shutil.copy(ROOT / script, copy)
        (workdir / ("env-" + copy.name)).write_text("x")
        for f in ("args", "seen", "log", "props"):
            (self.dir / f).unlink(missing_ok=True)
        environ = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.home), "STUB_DIR": str(self.dir),
                   "CTX_WORKFLOW": workflow, "ACTIVE": active}
        environ.update(settings)
        proc = subprocess.run([shell, str(copy)], env=environ, cwd=self.dir, capture_output=True, text=True)
        self.env_file_left = (workdir / ("env-" + copy.name)).exists()
        return proc.returncode

    def read(self, name):
        p = self.dir / name
        return p.read_text() if p.exists() else ""

    def args(self):
        return self.read("args").splitlines()

    def seen(self):
        return dict(line.split("=", 1) for line in self.read("seen").splitlines())

    def close(self):
        shutil.rmtree(self.dir)


# What installer v1.3.1 passes whole: shell syntax but no quote, backslash, whitespace or glob.
AWKWARD = "p@ss$HOME`id`!&;|(#:x"
# What rke2_app.sh refuses for it (registries.yaml unescaped, the image push unquoted).
REFUSED = ["Zq9\"x", "Zq9\\x", "Zq9 x", "Zq9\tx", "Zq9*x", "Zq9?x", "Zq9[x"]


class StandaloneAppTests(unittest.TestCase):
    script = "tech-ops/scripts/rke2_app.sh"

    def setUp(self):
        self.bed = Bed()

    def tearDown(self):
        self.bed.close()

    def run_app(self, shell, workflow="install", **settings):
        return self.bed.run(shell, self.script, settings, workflow)

    def test_tasks(self):
        reg = {"REG_URL": "reg.example.com:443", "REG_USER": "admin", "REG_PASS": AWKWARD}
        cases = [
            ({"RUN_ARG": "install"}, ["install"]),
            ({"RUN_ARG": "install", "TLS_SAN": "rke2.example.com", **reg},
             ["install", "-tls-san", "rke2.example.com", "-registry", "reg.example.com:443", "admin", AWKWARD]),
            ({"RUN_ARG": "install push", **reg}, ["install", "push", "-registry", "reg.example.com:443", "admin", AWKWARD]),
            ({"RUN_ARG": "push", "TLS_SAN": "rke2.example.com", **reg}, ["push", "-registry", "reg.example.com:443", "admin", AWKWARD]),
            ({"RUN_ARG": "save", "TLS_SAN": "rke2.example.com", **reg}, ["save"]),
            ({"RUN_ARG": "install velero", **reg}, ["install", "velero"]),
            ({"RUN_ARG": "install monitoring", "TLS_SAN": "x.example.com"}, ["install", "monitoring"]),
            ({"RUN_ARG": "uninstall", **reg}, ["uninstall"]),
            ({"RUN_ARG": "join", "JOIN_MODE": "server", "JOIN_SERVER": "10.0.0.9", "JOIN_TOKEN": "K10a b*",
              "TLS_SAN": "rke2.example.com", **reg},
             ["join", "server", "10.0.0.9", "K10a b*", "-tls-san", "rke2.example.com", "-registry",
              "reg.example.com:443", "admin", AWKWARD]),
            ({"RUN_ARG": "join", "JOIN_MODE": "agent", "JOIN_SERVER": "10.0.0.9", "JOIN_TOKEN": "K10x",
              "TLS_SAN": "rke2.example.com"}, ["join", "agent", "10.0.0.9", "K10x"]),
            ({"RUN_ARG": "None", "TLS_SAN": "None", "REG_URL": "None"}, ["install"]),
        ]
        for shell in SHELLS:
            for settings, expected in cases:
                with self.subTest(shell=shell, task=settings["RUN_ARG"]):
                    self.assertEqual(self.run_app(shell, **settings), 0, self.bed.read("log"))
                    self.assertEqual(self.bed.args(), expected)
                    self.assertFalse(self.bed.env_file_left)
                    self.assertNotIn(AWKWARD, self.bed.read("log"))
                    self.assertNotIn("K10a b*", self.bed.read("log"))
                    seen = self.bed.seen()
                    self.assertEqual(seen["REG_PASS"], "<unset>")
                    self.assertEqual(seen["JOIN_TOKEN"], "<unset>")

    def test_refusals(self):
        cases = [
            {"RUN_ARG": "push"},
            {"RUN_ARG": "install push"},
            {"RUN_ARG": "install", "REG_URL": "reg.example.com:443", "REG_USER": "admin", "REG_PASS": "None"},
            {"RUN_ARG": "join", "JOIN_MODE": "", "JOIN_SERVER": "x.example.com", "JOIN_TOKEN": "K10"},
            {"RUN_ARG": "join", "JOIN_MODE": "server", "JOIN_SERVER": "", "JOIN_TOKEN": "K10"},
            {"RUN_ARG": "join", "JOIN_MODE": "agent", "JOIN_SERVER": "x.example.com", "JOIN_TOKEN": "None"},
            {"RUN_ARG": "upgrade"},
        ]
        for shell in SHELLS:
            for settings in cases:
                with self.subTest(shell=shell, settings=settings):
                    self.assertEqual(self.run_app(shell, **settings), 1)
                    self.assertEqual(self.bed.args(), [])

    def test_uninstall_task_only_in_install(self):
        for shell in SHELLS:
            for workflow in ("update", "heal"):
                with self.subTest(shell=shell, workflow=workflow):
                    self.assertEqual(self.run_app(shell, workflow, RUN_ARG="uninstall"), 0)
                    self.assertEqual(self.bed.args(), [])

    def test_reinstall_reruns_install(self):
        for shell in SHELLS:
            self.assertEqual(self.run_app(shell, "update", RUN_ARG="install"), 0)
            self.assertEqual(self.bed.args(), ["install"])

    def test_registry_password_refusals(self):
        for shell in SHELLS:
            for task in ("install", "push", "join"):
                for pw in REFUSED:
                    with self.subTest(shell=shell, task=task, pw=pw):
                        rc = self.run_app(shell, RUN_ARG=task, JOIN_MODE="agent", JOIN_SERVER="x.example.com",
                                          JOIN_TOKEN="K10", REG_URL="reg.example.com:443", REG_USER="u", REG_PASS=pw)
                        self.assertEqual(rc, 1)
                        self.assertEqual(self.bed.args(), [])
                        self.assertNotIn(pw, self.bed.read("log"))
            # save doesn't use the registry, so its password isn't checked
            self.assertEqual(self.run_app(shell, RUN_ARG="save", REG_URL="reg.example.com:443", REG_USER="u",
                                          REG_PASS="a b"), 0)

    def test_installer_failure_is_exit_1(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                self.assertEqual(self.run_app(shell, RUN_ARG="install", FAKE_RC="7"), 1)
                self.assertIn("exit code 7", self.bed.read("log"))

    def test_settings_pass_through(self):
        for shell in SHELLS:
            self.run_app(shell, RUN_ARG="install", RKE2_VERSION="v1.34.5+rke2r1", CLUSTER_NAME="edge-lab",
                         RKE2_FORCE_ONLINE="true")
            seen = self.bed.seen()
            self.assertEqual(seen["RKE2_VERSION"], "v1.34.5+rke2r1")
            self.assertEqual(seen["RKE2_FORCE_ONLINE"], "true")
            self.assertEqual(seen["TLS_SAN"], "<unset>")


class MultiNodeAppTests(unittest.TestCase):
    script = "multi-node/scripts/rke2_app.sh"
    server_only = {"CLUSTER_CIDR": "10.42.0.0/16", "PVC_DATA": "/opt/pvc"}

    def setUp(self):
        self.bed = Bed()

    def tearDown(self):
        self.bed.close()

    def test_roles(self):
        reg = {"REG_URL": "reg.example.com:443", "REG_USER": "admin", "REG_PASS": AWKWARD}
        join = {"JOIN_SERVER": "10.0.0.5", "JOIN_TOKEN": "K10abc::server:def"}
        cases = [
            ({"ROLE": "cp1"}, ["install"]),
            ({"ROLE": "cp1", "PUSH_IMAGES": "true"}, ["install"]),
            ({"ROLE": "cp1", "PUSH_IMAGES": "true", "TLS_SAN": "rke2.example.com", **reg},
             ["install", "push", "-tls-san", "rke2.example.com", "-registry", "reg.example.com:443", "admin", AWKWARD]),
            ({"ROLE": "cp1", "PUSH_IMAGES": "false", **reg}, ["install", "-registry", "reg.example.com:443", "admin", AWKWARD]),
            ({"ROLE": "cp", **join}, ["join", "server", "10.0.0.5", "K10abc::server:def"]),
            ({"ROLE": "cp", "TLS_SAN": "rke2.example.com", **join, **reg},
             ["join", "server", "rke2.example.com", "K10abc::server:def", "-tls-san", "rke2.example.com",
              "-registry", "reg.example.com:443", "admin", AWKWARD]),
            ({"ROLE": "agent", "TLS_SAN": "rke2.example.com", **join, **reg},
             ["join", "agent", "rke2.example.com", "K10abc::server:def", "-registry", "reg.example.com:443", "admin", AWKWARD]),
            ({"ROLE": "agent", "TLS_SAN": "None", "REG_URL": "None", **join}, ["join", "agent", "10.0.0.5", "K10abc::server:def"]),
        ]
        for shell in SHELLS:
            for settings, expected in cases:
                with self.subTest(shell=shell, settings=settings):
                    self.assertEqual(self.bed.run(shell, self.script, {**settings, **self.server_only}), 0,
                                     self.bed.read("log"))
                    self.assertEqual(self.bed.args(), expected)
                    self.assertFalse(self.bed.env_file_left)
                    self.assertNotIn("K10abc", self.bed.read("log"))
                    self.assertNotIn(AWKWARD, self.bed.read("log"))
                    seen = self.bed.seen()
                    self.assertEqual(seen["JOIN_TOKEN"], "<unset>")
                    # Agents don't get the server-only settings, so the installer doesn't warn.
                    agent = settings["ROLE"] == "agent"
                    self.assertEqual(seen["CLUSTER_CIDR"] == "<unset>", agent)
                    self.assertEqual(seen["PVC_DATA"] == "<unset>", agent)

    def test_registry_password_refusals(self):
        for shell in SHELLS:
            for role in ("cp1", "cp", "agent"):
                for pw in REFUSED:
                    with self.subTest(shell=shell, role=role, pw=pw):
                        rc = self.bed.run(shell, self.script, {"ROLE": role, "JOIN_SERVER": "10.0.0.5",
                                                               "JOIN_TOKEN": "K10x", "REG_URL": "reg.example.com:443",
                                                               "REG_USER": "u", "REG_PASS": pw})
                        self.assertEqual(rc, 1)
                        self.assertEqual(self.bed.args(), [])

    def test_token_check(self):
        for shell in SHELLS:
            for token in ("N/A", "", "None", "secret"):
                for role in ("cp", "agent"):
                    with self.subTest(shell=shell, token=token, role=role):
                        rc = self.bed.run(shell, self.script, {"ROLE": role, "JOIN_SERVER": "10.0.0.5", "JOIN_TOKEN": token})
                        self.assertEqual(rc, 1)
                        self.assertEqual(self.bed.args(), [])

    def test_unknown_role(self):
        for shell in SHELLS:
            self.assertEqual(self.bed.run(shell, self.script, {}), 1)


class StopTests(unittest.TestCase):
    def setUp(self):
        self.bed = Bed()

    def tearDown(self):
        self.bed.close()

    def test_standalone(self):
        paths = {"RKE2_DATA": "/opt/rke2", "PVC_DATA": "/opt/pvc"}
        for shell in SHELLS:
            for workflow, task, expected in [("uninstall", "install", ["uninstall"]), ("uninstall", "join", ["uninstall"]),
                                             ("uninstall", "save", []), ("uninstall", "uninstall", []),
                                             ("heal", "install", []), ("update", "install", [])]:
                with self.subTest(shell=shell, workflow=workflow, task=task):
                    rc = self.bed.run(shell, "tech-ops/scripts/rke2_stop.sh", {"RUN_ARG": task, **paths}, workflow)
                    self.assertEqual(rc, 0)
                    self.assertEqual(self.bed.args(), expected)
                    self.assertFalse(self.bed.env_file_left)
                    if expected:
                        self.assertEqual(self.bed.seen()["RKE2_DATA"], "/opt/rke2")

    def test_multi_node(self):
        for shell in SHELLS:
            for workflow, expected in [("uninstall", ["uninstall"]), ("scale", ["uninstall"]), ("heal", []), ("update", [])]:
                with self.subTest(shell=shell, workflow=workflow):
                    rc = self.bed.run(shell, "multi-node/scripts/rke2_stop.sh", {"PVC_DATA": "/opt/pvc"}, workflow)
                    self.assertEqual(rc, 0)
                    self.assertEqual(self.bed.args(), expected)
                    if expected:
                        self.assertEqual(self.bed.seen()["PVC_DATA"], "/opt/pvc")


class PrecheckTests(unittest.TestCase):
    url = "https://github.com/Chubtoad5/rke2-installer/releases/download/v1.3.1/rke2_installer.sh"
    body = b"#!/bin/sh\nSCRIPT_VERSION=\"1.3.1\"\n"

    def setUp(self):
        self.bed = Bed()
        (self.bed.home / "rke2_installer.sh").unlink()

    def tearDown(self):
        self.bed.close()

    def serve(self, body=None, sums=None):
        for f in self.bed.www.iterdir():
            f.unlink()
        if body is not None:
            (self.bed.www / "rke2_installer.sh").write_bytes(body)
        if sums is not None:
            (self.bed.www / "SHA256SUMS").write_text(sums)

    def run_precheck(self, shell, script, **settings):
        target = self.bed.home / "rke2_installer.sh"
        target.unlink(missing_ok=True)
        rc = self.bed.run(shell, script, {"OFFLINE_MODE": "False", "SCRIPT_URL": self.url, **settings})
        return rc, target.exists()

    def test_checksum(self):
        good = hashlib.sha256(self.body).hexdigest()
        cases = [
            ("match", self.body, f"{good}  rke2_installer.sh\n", 0, True),
            ("match, binary mode", self.body, f"{good} *rke2_installer.sh\n", 0, True),
            ("mismatch", self.body + b"x", f"{good}  rke2_installer.sh\n", 1, False),
            ("no entry", self.body, f"{good}  other.sh\n", 1, False),
            ("no SHA256SUMS", self.body, None, 1, False),
            ("download fails", None, f"{good}  rke2_installer.sh\n", 1, False),
        ]
        for script in ("tech-ops/scripts/env_precheck.sh", "multi-node/scripts/env_precheck.sh"):
            for shell in SHELLS:
                for name, body, sums, rc, kept in cases:
                    with self.subTest(script=script, shell=shell, case=name):
                        self.serve(body, sums)
                        self.assertEqual(self.run_precheck(shell, script), (rc, kept), self.bed.read("log"))
                        self.assertFalse(self.bed.env_file_left)
                        self.assertFalse((self.bed.home / "rke2_installer.sh.download").exists())

    def test_not_a_release_asset(self):
        self.serve(self.body)
        for shell in SHELLS:
            rc, kept = self.run_precheck(shell, "tech-ops/scripts/env_precheck.sh",
                                         SCRIPT_URL="https://example.com/raw/abc/rke2_installer.sh")
            self.assertEqual((rc, kept), (0, True))
            self.assertIn("isn't a GitHub release asset", self.bed.read("log"))


class StandalonePostcheckTests(unittest.TestCase):
    script = "tech-ops/scripts/env_postcheck.sh"

    def setUp(self):
        self.bed = Bed()

    def tearDown(self):
        self.bed.close()

    def test_rke2_must_run_after_install(self):
        for shell in SHELLS:
            for task, active, rc in [("install", "", 1), ("join", "", 1), ("install push", "", 1),
                                     ("save", "", 0), ("uninstall", "", 0), ("push", "", 0),
                                     ("join", "rke2-agent", 0)]:
                with self.subTest(shell=shell, task=task, active=active):
                    self.assertEqual(self.bed.run(shell, self.script, {"RUN_ARG": task}, active=active), rc,
                                     self.bed.read("log"))
                    self.assertFalse(self.bed.env_file_left)

    def test_token_from_data_path(self):
        data = self.bed.dir / "rke2data"
        (data / "server").mkdir(parents=True)
        (data / "bin").mkdir()
        (data / "server" / "node-token").write_text("K10tok::server:x")
        kubectl = data / "bin" / "kubectl"
        kubectl.write_text("#!/bin/sh\nexit 0\n")
        kubectl.chmod(0o755)
        for shell in SHELLS:
            self.assertEqual(self.bed.run(shell, self.script, {"RUN_ARG": "install", "RKE2_DATA": str(data)},
                                          active="rke2-server"), 0, self.bed.read("log"))
            props = self.bed.read("props")
            self.assertIn("capabilities.rke2_join_token=K10tok::server:x", props)
            self.assertIn("capabilities.rke2_node_status=Ready", props)

    def test_save_package_in_home(self):
        (self.bed.home / "rke2-save.tar.gz").write_text("x")
        for shell in SHELLS:
            self.assertEqual(self.bed.run(shell, self.script, {"RUN_ARG": "save", "UPLOAD_OFFLINE_PACKAGE": "False"}), 0)
            self.assertIn("capabilities.offline_package_name=rke2-save.tar.gz", self.bed.read("props"))


if __name__ == "__main__":
    unittest.main()
