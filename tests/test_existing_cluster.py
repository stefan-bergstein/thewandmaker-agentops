"""Offline deployment regressions; no real credentials or cluster access."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    result = importlib.util.module_from_spec(spec)
    with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
        spec.loader.exec_module(result)
    return result


class ExistingClusterTests(unittest.TestCase):
    def setUp(self):
        self.runner = module("runner", "run-openshell.py")
        self.model = {"model": "test-model", "modelendpoint": "https://model.example/v1/chat/completions",
                      "modelkey": "dummy-test-key"}

    def run_script(self, settings):
        with patch.object(self.runner, "load_env", return_value=settings), \
             patch.object(self.runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch.object(self.runner.sys, "argv", ["runner", "gitops/02-openshell/provider-maas.sh"]), \
             self.assertRaises(SystemExit) as result:
            self.runner.main()
        return result.exception.code, run.call_args_list

    def test_local_provider_uses_existing_auth_and_no_ssh(self):
        with patch.dict(os.environ, {"KUBECONFIG": "/custom/config"}):
            code, calls = self.run_script(self.model)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertEqual(args[0][0], "bash")
        self.assertEqual(kwargs["env"]["KUBECONFIG"], "/custom/config")
        self.assertEqual(kwargs["env"]["MAAS_BASE_URL"], "https://model.example/v1")
        self.assertEqual(kwargs["env"]["OPENAI_API_KEY"], "dummy-test-key")
        self.assertNotIn("dummy-test-key", " ".join(args[0]))

    def test_default_oc_context_is_not_replaced(self):
        with patch.dict(os.environ, {}, clear=True):
            _, calls = self.run_script(self.model)
        self.assertNotIn("KUBECONFIG", calls[0].kwargs["env"])

    def test_connect_does_not_need_model_or_rosa_settings(self):
        code, calls = self.run_script({})
        self.assertEqual(code, 0)
        self.assertEqual(calls[0].args[0][0], "bash")

    def test_partial_bastion_configuration_fails_before_running_commands(self):
        for settings in ({"BASTION_HOST": "example"}, {"BASTION_USER": "user"}):
            with self.subTest(settings=settings):
                code, calls = self.run_script(settings)
                self.assertIn("both", code)
                self.assertEqual(calls, [])

    def test_optional_remote_mode_transmits_keys_over_stdin(self):
        code, calls = self.run_script(dict(self.model, BASTION_HOST="example", BASTION_USER="operator"))
        self.assertEqual(code, 0)
        self.assertEqual([c.args[0][0] for c in calls], ["ssh", "scp", "ssh"])
        self.assertIn("dummy-test-key", calls[-1].kwargs["input"])
        for call in calls:
            self.assertNotIn("dummy-test-key", " ".join(call.args[0]))

    def test_preflight_accepts_model_only_configuration(self):
        preflight = module("preflight", "preflight.py")
        with patch.object(preflight, "load_env", return_value=self.model), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            preflight.check_env()
        self.assertEqual(preflight.missing, [])
        self.assertNotIn("dummy-test-key", output.getvalue())

    def test_preflight_uses_exported_kubeconfig(self):
        with patch.dict(os.environ, {"KUBECONFIG": "/custom/config"}):
            preflight = module("preflight", "preflight.py")
        self.assertEqual(preflight.OCENV["KUBECONFIG"], "/custom/config")

    def test_dashboard_runs_forward_locally_without_ssh(self):
        dashboard = module("dashboard", "dashboard.py")
        with patch.object(dashboard.subprocess, "run") as run:
            dashboard.run_cli(None, "openshell status")
        self.assertEqual(run.call_args.args[0], ["bash", "-s"])

    def test_platform_plan_needs_no_cloud_or_remote_setup(self):
        result = subprocess.run(["make", "-n", "up-platform"], cwd=ROOT,
                                text=True, capture_output=True, check=True)
        self.assertNotIn("scripts/cluster-access.py", result.stdout)
        self.assertNotIn("scripts/tf.py", result.stdout)
        self.assertNotIn("install-cli-linux.sh", result.stdout)
        self.assertIn("connect-cli.sh", result.stdout)
        self.assertIn("apprentice.sh", result.stdout)

    def test_rehearsal_verifies_login_without_saved_admin_credentials(self):
        with patch.object(sys, "argv", ["prepare.py"]):
            prepare = module("prepare", "prepare.py")
        with patch.object(prepare, "oc", return_value="cluster-operator"), \
             patch.object(prepare, "run") as run, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(prepare.login())
        run.assert_not_called()

    def test_links_with_secrets_needs_no_admin_password_file(self):
        links = module("links", "links.py")
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(links, "ROOT", directory), \
             patch.object(links, "env", return_value={}), \
             patch.object(links, "oc", return_value="demo.example"), \
             patch.object(sys, "argv", ["links.py", "--secrets"]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            links.main()
        self.assertIn("identity provider", output.getvalue())
        self.assertNotIn("cluster-admin-password", output.getvalue())

    def test_standalone_helpers_keep_exported_cluster_context(self):
        for filename in ("campaign.py", "night.py", "oracle.py", "captures.py", "deck-live.py", "links.py"):
            with self.subTest(filename=filename), \
                 patch.dict(os.environ, {"KUBECONFIG": "/custom/config"}):
                module("helper_" + filename.replace(".", "_"), filename)
                self.assertEqual(os.environ["KUBECONFIG"], "/custom/config")

    def test_failed_local_script_returns_failure(self):
        with patch.object(self.runner, "load_env", return_value={}), \
             patch.object(self.runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 7)), \
             patch.object(sys, "argv", ["runner", "script.sh"]), \
             self.assertRaises(SystemExit) as result:
            self.runner.main()
        self.assertEqual(result.exception.code, 7)

    def test_optional_deck_password_skips_empty_apply(self):
        deck_login = module("deck_login", "deck-login.py")
        with patch.object(deck_login.subprocess, "run") as run:
            deck_login.configure("")
        run.assert_not_called()

    def test_deck_password_is_sent_over_stdin(self):
        deck_login = module("deck_login", "deck-login.py")
        with patch.object(deck_login.subprocess, "run") as run:
            deck_login.configure("dummy-test-password")
        self.assertEqual(run.call_args.args[0], ["oc", "apply", "-f", "-"])
        self.assertIn('"kind": "Secret"', run.call_args.kwargs["input"])
        self.assertNotIn("dummy-test-password", " ".join(run.call_args.args[0]))

    def test_host_base64_encoding_preserves_config_bytes(self):
        # Check the actual portable OpenSSL syntax used by the local sandbox scripts.
        import base64
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "config.json"
            source.write_bytes(b'{"test": "portable encoding"}\n')
            result = subprocess.run(["openssl", "base64", "-A", "-in", str(source)],
                                    capture_output=True, check=True)
            self.assertEqual(base64.b64decode(result.stdout), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
