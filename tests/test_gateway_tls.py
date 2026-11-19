"""Exercise connection.sh against fake CLIs, including the packaged TLS import bug."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parent.parent


class GatewayTLSTests(unittest.TestCase):
    def connect(self, existing=False, fail_add=False):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            bin_dir = base / "bin"
            bin_dir.mkdir()
            config = base / "config"
            gateway = config / "openshell/gateways/olli"
            gateway.mkdir(parents=True)
            (gateway / "mtls").mkdir()
            # Start with a different local CA and optionally an older cluster registration.
            (gateway / "mtls/ca.crt").write_text("old-ca")
            if existing:
                (gateway / "endpoint").write_text("https://previous-cluster.example")
            programs = {
                "oc": r'''
                    import base64, sys
                    args = sys.argv[1:]
                    if args == ["whoami"]:
                        print("operator")
                    elif "route" in args:
                        print("cluster.example")
                    else:
                        field = args[-1]
                        data = "cluster-ca" if "ca\\.crt" in field else "cluster-cert" if "tls\\.crt" in field else "dummy-key"
                        print(base64.b64encode(data.encode()).decode(), end="")
                ''',
                "openshell": r'''
                    import json, os, pathlib, sys
                    args = sys.argv[1:]
                    config = pathlib.Path(os.environ["XDG_CONFIG_HOME"])
                    gateway = config / "openshell/gateways/olli"
                    with (config / "calls").open("a") as log:
                        log.write(json.dumps(args) + "\n")
                    if args[:2] == ["gateway", "add"]:
                        if os.environ.get("TEST_FAIL_ADD"):
                            sys.exit("registration permission denied")
                        if (gateway / "endpoint").exists():
                            sys.exit("Gateway 'olli' already exists.")
                        # Reproduce OpenShell's package-managed TLS import unless disabled.
                        if os.environ.get("OPENSHELL_LOCAL_TLS_DIR") != "/dev/null":
                            (gateway / "mtls/ca.crt").write_text("package-ca")
                        (gateway / "endpoint").write_text(args[2])
                    elif args[:2] == ["gateway", "remove"]:
                        (gateway / "endpoint").unlink()
                    elif args[0] == "status":
                        if (gateway / "mtls/ca.crt").read_text() != "cluster-ca":
                            sys.exit("invalid peer certificate: BadSignature")
                        if (gateway / "endpoint").read_text() != "https://cluster.example":
                            sys.exit("stale endpoint")
                        print("Connected; authenticated using cluster mTLS")
                ''',
            }
            for name, body in programs.items():
                path = bin_dir / name
                path.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body).lstrip())
                path.chmod(0o755)
            env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
                       XDG_CONFIG_HOME=str(config))
            env.pop("TEST_FAIL_ADD", None)
            if fail_add:
                env["TEST_FAIL_ADD"] = "1"
            result = subprocess.run(["bash", str(ROOT / "gitops/02-openshell/connect-cli.sh")],
                                    env=env, capture_output=True, text=True)
            calls = [json.loads(line) for line in (config / "calls").read_text().splitlines()]
            mode = (gateway / "mtls/tls.key").stat().st_mode & 0o777
            return result, calls, mode

    def test_first_registration_keeps_cluster_certificates(self):
        result, calls, mode = self.connect()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("authenticated using cluster mTLS", result.stdout)
        self.assertEqual(mode, 0o600)
        self.assertFalse(any("--gateway-insecure" in call for call in calls))

    def test_reconnect_refreshes_old_endpoint_and_certificates(self):
        result, calls, _ = self.connect(existing=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["gateway", "remove", "olli"], calls)
        self.assertIn("Connected", result.stdout)

    def test_registration_failure_stops_before_status(self):
        result, calls, _ = self.connect(fail_add=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("permission denied", result.stderr)
        self.assertFalse(any(call[0] == "status" for call in calls))


if __name__ == "__main__":
    unittest.main()
