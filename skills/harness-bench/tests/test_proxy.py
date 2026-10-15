"""Tests for bench_proxy.py against the fake daemon. No model, no network beyond loopback."""

import json
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "bench_proxy.py"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SCRIPT.parent))

from fake_daemon import FakeDaemon  # noqa: E402
import bench_proxy  # noqa: E402

TAG = "fake:cloud"
TOOLS = [{"type": "function", "function": {"name": "shell", "parameters": {"type": "object"}}}]


class ProxyBase(unittest.TestCase):
    think = "low"
    temperature = 0.0

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bench-proxy-test-"))
        self.daemon = FakeDaemon()
        self.log = self.tmp / "proxy.jsonl"
        port_file = self.tmp / "port"
        self.exchanges = self.tmp / "exchanges.jsonl"
        args = [sys.executable, str(SCRIPT), "--tag", TAG, "--log", str(self.log), "--port-file", str(port_file),
                "--upstream", f"127.0.0.1:{self.daemon.port}", "--exchanges", str(self.exchanges)]
        if self.think is not None:
            args += ["--think", self.think]
        if self.temperature is not None:
            args += ["--temperature", str(self.temperature)]
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        end = time.time() + 30
        while not port_file.exists() and time.time() < end:
            time.sleep(0.05)
        self.assertTrue(port_file.exists(), "proxy never wrote its port")
        self.base = f"http://127.0.0.1:{port_file.read_text()}"

    def tearDown(self):
        self.proc.terminate()
        self.proc.wait(timeout=10)
        self.proc.stderr.close()
        self.daemon.close()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def records(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []


class TestRefusals(ProxyBase):
    def test_wrong_model_is_refused_before_the_daemon(self):
        code, _ = self.post("/v1/chat/completions", {"model": "other:cloud", "messages": [], "tools": TOOLS})
        self.assertEqual(code, 403)
        self.assertEqual(self.daemon.received, [])
        self.assertIn("model not under test", self.records()[0]["refused"])

    def test_management_and_unknown_endpoints_are_refused(self):
        for path in ("/api/pull", "/api/push", "/api/create", "/api/copy", "/api/delete", "/api/generate", "/api/embed"):
            code, _ = self.post(path, {"model": TAG})
            self.assertEqual(code, 403, path)
        code, _ = self.get("/api/ps")
        self.assertEqual(code, 403)
        self.assertEqual(self.daemon.received, [])

    def test_listing_endpoints_are_forwarded(self):
        code, body = self.get("/api/tags")
        self.assertEqual(code, 200)
        self.assertIn(b"fake:cloud", body)
        self.assertEqual(self.daemon.received[0][:2], ("GET", "/api/tags"))

    def test_non_loopback_upstream_is_refused(self):
        self.assertEqual(bench_proxy.main(["--tag", TAG, "--log", str(self.tmp / "x"), "--port-file",
                                           str(self.tmp / "p"), "--upstream", "10.0.0.1:11434"]), 2)
        self.assertFalse((self.tmp / "p").exists())


class TestV1(ProxyBase):
    def test_task_call_is_pinned_and_counted(self):
        body = {"model": TAG, "stream": True, "tools": TOOLS, "reasoning_effort": "max", "temperature": 0.7,
                "messages": [{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}]}
        code, data = self.post("/v1/chat/completions", body)
        self.assertEqual(code, 200)
        self.assertIn(b"[DONE]", data)
        sent = self.daemon.received[-1][2]
        self.assertEqual(sent["reasoning_effort"], "low")
        self.assertEqual(sent["temperature"], 0.0)
        self.assertTrue(sent["stream_options"]["include_usage"])
        rec = self.records()[-1]
        self.assertEqual(rec["call"], "task")
        self.assertEqual((rec["think_sent"], rec["think_applied"]), ("max", "low"))
        self.assertEqual((rec["temperature_sent"], rec["temperature_applied"]), (0.7, 0.0))
        self.assertEqual((rec["prompt_tokens"], rec["output_tokens"]), (11, 7))
        self.assertEqual((rec["tool_calls"], rec["malformed_tool_calls"]), (1, 0))
        self.assertEqual(len(rec["system_hash"]), 16)

    def test_exchange_holds_the_forwarded_request_and_assembled_answer(self):
        self.post("/v1/chat/completions", {"model": TAG, "stream": True, "tools": TOOLS, "reasoning_effort": "max",
                                           "messages": [{"role": "user", "content": "hi"}]})
        ex = [json.loads(x) for x in self.exchanges.read_text().splitlines()]
        self.assertEqual(len(ex), 1)
        self.assertEqual(ex[0]["request"]["reasoning_effort"], "low")
        self.assertEqual(ex[0]["request"]["messages"], [{"role": "user", "content": "hi"}])
        self.assertEqual(ex[0]["response"]["tool_calls"], [{"name": "shell", "arguments": '{"command": "ls"}'}])
        self.assertEqual(ex[0]["call"], "task")

    def test_auxiliary_call_passes_through_unpinned(self):
        body = {"model": TAG, "stream": True, "reasoning_effort": "none",
                "messages": [{"role": "user", "content": "name this session"}]}
        self.post("/v1/chat/completions", body)
        sent = self.daemon.received[-1][2]
        self.assertEqual(sent["reasoning_effort"], "none")
        self.assertNotIn("temperature", sent)
        rec = self.records()[-1]
        self.assertEqual((rec["call"], rec["think_sent"], rec["think_applied"]), ("aux", "none", "none"))
        self.assertEqual(rec["output_tokens"], 7)

    def test_developer_role_counts_as_the_system_prompt(self):
        self.post("/v1/chat/completions", {"model": TAG, "stream": True, "tools": TOOLS,
                                           "messages": [{"role": "developer", "content": "be terse"}]})
        same = {"model": TAG, "stream": True, "tools": TOOLS, "messages": [{"role": "system", "content": "be terse"}]}
        self.post("/v1/chat/completions", same)
        a, b = self.records()[-2:]
        self.assertEqual(a["system_hash"], b["system_hash"])
        self.assertIsNotNone(a["system_hash"])
        self.assertEqual((a["roles"], b["roles"]), (["developer"], ["system"]))

    def test_malformed_tool_arguments_are_counted(self):
        self.daemon.bad_args = True
        self.post("/v1/chat/completions", {"model": TAG, "stream": True, "tools": TOOLS, "messages": []})
        rec = self.records()[-1]
        self.assertEqual((rec["tool_calls"], rec["malformed_tool_calls"]), (1, 1))

    def test_non_streaming_response_is_counted(self):
        code, data = self.post("/v1/chat/completions", {"model": TAG, "tools": TOOLS, "messages": []})
        self.assertEqual(code, 200)
        self.assertIn(b"tool_calls", data)
        rec = self.records()[-1]
        self.assertEqual((rec["prompt_tokens"], rec["output_tokens"], rec["tool_calls"]), (11, 7, 1))


class TestNativeChat(ProxyBase):
    def test_api_chat_task_call_is_pinned_and_counted(self):
        body = {"model": TAG, "tools": TOOLS, "think": True, "options": {"num_ctx": 8192},
                "messages": [{"role": "user", "content": "hi"}]}
        code, data = self.post("/api/chat", body)
        self.assertEqual(code, 200)
        self.assertIn(b'"done": true', data)
        sent = self.daemon.received[-1][2]
        self.assertEqual(sent["think"], "low")
        self.assertEqual(sent["options"], {"num_ctx": 8192, "temperature": 0.0})
        rec = self.records()[-1]
        self.assertEqual((rec["think_sent"], rec["think_applied"]), (True, "low"))
        self.assertEqual((rec["prompt_tokens"], rec["output_tokens"], rec["tool_calls"]), (13, 5, 1))
        self.assertIsNone(rec["system_hash"])


class TestRecordOnly(ProxyBase):
    think = None
    temperature = None

    def test_without_pins_the_task_call_is_recorded_unchanged(self):
        self.post("/v1/chat/completions", {"model": TAG, "stream": True, "tools": TOOLS,
                                           "reasoning_effort": "high", "messages": []})
        sent = self.daemon.received[-1][2]
        self.assertEqual(sent["reasoning_effort"], "high")
        self.assertNotIn("temperature", sent)
        rec = self.records()[-1]
        self.assertEqual((rec["think_sent"], rec["think_applied"]), ("high", "high"))


if __name__ == "__main__":
    unittest.main()
