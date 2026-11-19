"""Protect pre-existing OLM and DataScienceCluster resources during installation."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("installer", ROOT / "scripts/install-platform-resources.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ExistingOperatorsTests(unittest.TestCase):
    def setUp(self):
        self.resources = [
            {"kind": "Namespace", "metadata": {"name": "operator-system"}},
            {"kind": "OperatorGroup", "metadata": {"name": "demo-group", "namespace": "operator-system"}},
            {"kind": "Subscription", "metadata": {"name": "demo-sub", "namespace": "operator-system"},
             "spec": {"name": "test-operator", "channel": "demo-channel"}},
        ]

    def test_oc_create_json_stream_is_read_as_multiple_resources(self):
        from subprocess import CompletedProcess
        output = "\n".join(json.dumps(item) for item in self.resources)
        with patch.object(installer.subprocess, "run", return_value=CompletedProcess([], 0, stdout=output)):
            self.assertEqual(installer.manifest("unused.yaml"), self.resources)

    def test_existing_operatorgroup_and_package_subscription_are_reused(self):
        existing = [
            {"items": [{"metadata": {"name": "existing-group"}}]},
            {"items": [{"metadata": {"name": "existing-sub"},
                        "spec": {"name": "test-operator", "channel": "keep-channel"}}]},
        ]
        with patch.object(installer, "manifest", return_value=self.resources), \
             patch.object(installer, "oc_json", side_effect=existing), \
             patch.object(installer, "apply") as apply, \
             contextlib.redirect_stdout(io.StringIO()):
            installer.install_operators()
        self.assertEqual([call.args[0]["kind"] for call in apply.call_args_list], ["Namespace"])
        self.assertEqual(existing[1]["items"][0]["spec"]["channel"], "keep-channel")

    def test_fresh_namespaces_receive_operatorgroup_and_subscription(self):
        with patch.object(installer, "manifest", return_value=self.resources), \
             patch.object(installer, "oc_json", return_value={"items": []}), \
             patch.object(installer, "apply") as apply:
            installer.install_operators()
        self.assertEqual(len(apply.call_args_list), 3)

    def test_multiple_operatorgroups_fail_without_creating_another(self):
        with patch.object(installer, "manifest", return_value=self.resources), \
             patch.object(installer, "oc_json", return_value={"items": [{}, {}]}), \
             patch.object(installer, "apply") as apply, \
             self.assertRaises(SystemExit):
            installer.install_operators()
        self.assertEqual(len(apply.call_args_list), 1)

    def test_existing_ai_cluster_receives_only_required_enablements(self):
        desired = {"metadata": {"name": "default-dsc"}, "spec": {"components": {
            "kserve": {"managementState": "Managed", "nim": {"managementState": "Removed"}},
            "mcplifecycleoperator": {"managementState": "Managed"},
            "workbenches": {"managementState": "Removed"},
            "aipipelines": {"managementState": "Removed"},
            "modelregistry": {"managementState": "Removed"},
        }}}
        with patch.object(installer, "manifest", return_value=[desired]), \
             patch.object(installer, "oc_json", return_value={"items": [{"metadata": {"name": "my-existing-dsc"}}]}), \
             patch.object(installer.subprocess, "run") as run, \
             patch.object(installer, "apply") as apply, \
             contextlib.redirect_stdout(io.StringIO()):
            installer.install_ai()
        command = run.call_args_list[0].args[0]
        self.assertEqual(command[2:4], ["datasciencecluster", "my-existing-dsc"])
        self.assertIn("--type=merge", command)
        components = json.loads(command[command.index("-p") + 1])["spec"]["components"]
        self.assertEqual(set(components), {"kserve", "mcplifecycleoperator"})
        self.assertNotIn("nim", components["kserve"])
        apply.assert_not_called()
        self.assertIn("datasciencecluster/my-existing-dsc", run.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
