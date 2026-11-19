"""The backstage check must use the same authenticated model path as the apprentice."""
import asyncio
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("model_probe", ROOT / "apps/shop/shop/model_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ModelProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_uses_sandbox_inference_without_an_api_key(self):
        run = AsyncMock(return_value=(0, json.dumps({"choices": [{"message": {"content": "Wands."}}]}), ""))
        self.assertEqual(await probe.check_inference(run, "apprentice-2"), (True, ""))
        command, timeout = run.call_args.args
        self.assertEqual(command[:6], ["openshell", "sandbox", "exec", "-n", "apprentice-2", "--no-tty"])
        self.assertEqual(command[-1], "https://inference.local/v1/chat/completions")
        self.assertIn("--fail", command)
        self.assertGreater(timeout, 100)
        self.assertNotIn("Authorization", " ".join(command))

    async def test_http_failure_is_reported_without_echoing_output(self):
        run = AsyncMock(return_value=(22, "sensitive response", "curl: (22) The requested URL returned error: 401; private diagnostic"))
        ok, reason = await probe.check_inference(run)
        self.assertFalse(ok)
        self.assertIn("HTTP 401", reason)
        self.assertNotIn("sensitive", reason)
        self.assertNotIn("private", reason)

    async def test_empty_and_error_responses_fail_readiness(self):
        for response in ({"choices": [{"message": {"content": "  "}}]}, {"error": "unavailable"}, {}):
            with self.subTest(response=response):
                run = AsyncMock(return_value=(0, json.dumps(response), ""))
                self.assertFalse((await probe.check_inference(run))[0])

    async def test_malformed_response_fails_readiness(self):
        for output in ("invalid JSON", "null", "[]", '{"choices": [null]}'):
            with self.subTest(output=output):
                run = AsyncMock(return_value=(0, output, ""))
                self.assertFalse((await probe.check_inference(run))[0])

    async def test_timeout_fails_readiness(self):
        run = AsyncMock(side_effect=asyncio.TimeoutError)
        ok, reason = await probe.check_inference(run)
        self.assertFalse(ok)
        self.assertIn("timed out", reason)


if __name__ == "__main__":
    unittest.main()
