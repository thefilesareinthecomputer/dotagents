#!/usr/bin/env python3
"""Tests for skills/local-model-task/scripts/local_model_task.py.

Stdlib unittest. Every backend is a fake server on 127.0.0.1 (fake_backend.py);
no test reaches a real model or the network.
Run: python3 -m unittest discover -s skills/local-model-task/tests -v
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "local_model_task.py"
sys.path.insert(0, str(HERE))
from fake_backend import FakeBackend  # noqa: E402

spec = importlib.util.spec_from_file_location("model_task", SCRIPT)
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)


def backend(base_url, api="ollama", locality="local", model="qwen3.5:4b", **extra):
    return dict({"base_url": base_url, "api": api, "locality": locality, "default_model": model}, **extra)


# ---------------------------------------------------------------- unit

class TestLocality(unittest.TestCase):
    def test_loopback_hosts(self):
        for host in ("127.0.0.1", "127.0.0.2", "::1", "localhost"):
            self.assertTrue(mt.is_loopback_host(host), host)
        for host in ("0.0.0.0", "192.168.1.5", "10.0.0.1", "example.com", "::"):
            self.assertFalse(mt.is_loopback_host(host), host)

    def test_cloud_models(self):
        for model in ("kimi-k2.6:cloud", "gpt-oss:120b-cloud", "x:CLOUD", "x:120b-cloud@sha256:abc"):
            self.assertTrue(mt.is_cloud_model(model), model)
        for model in ("qwen3.5:4b", "cloudy:4b", "qwen3:4b-instruct"):
            self.assertFalse(mt.is_cloud_model(model), model)

    def test_local_backend_off_loopback_is_refused(self):
        with self.assertRaises(mt.TaskError) as cm:
            mt.validate_backend("x", backend("http://192.168.1.5:11434"))
        self.assertEqual(cm.exception.code, mt.EXIT_REFUSED)

    def test_ollama_com_is_refused_for_any_locality(self):
        for loc in ("local", "private", "hosted"):
            with self.assertRaises(mt.TaskError) as cm:
                mt.validate_backend("x", backend("https://api.ollama.com/v1", api="openai", locality=loc))
            self.assertEqual(cm.exception.code, mt.EXIT_REFUSED, loc)

    def test_plain_http_only_on_loopback(self):
        mt.validate_backend("tunnel", backend("http://127.0.0.1:4000/v1", api="openai", locality="private"))
        with self.assertRaises(mt.TaskError) as cm:
            mt.validate_backend("gw", backend("http://gw.example.com/v1", api="openai", locality="private"))
        self.assertEqual(cm.exception.code, mt.EXIT_ARGS)

    def test_credentials_in_url_rejected(self):
        with self.assertRaises(mt.TaskError):
            mt.validate_backend("gw", backend("https://user:pw@gw.example.com/v1", api="openai", locality="private"))

    def test_bad_fields_rejected(self):
        for bad in (backend("http://127.0.0.1:1", api="grpc"),
                    backend("http://127.0.0.1:1", locality="somewhere"),
                    backend("http://127.0.0.1:1", api_key_env="lower-case"),
                    {"base_url": "http://127.0.0.1:1"}):
            with self.assertRaises(mt.TaskError):
                mt.validate_backend("x", bad)


class TestListeners(unittest.TestCase):
    NETSTAT = (
        "Active Internet connections (including servers)\n"
        "Proto Recv-Q Send-Q  Local Address          Foreign Address        (state)\n"
        "tcp4       0      0  127.0.0.1.11434        *.*                    LISTEN\n"
        "tcp6       0      0  *.11434                *.*                    LISTEN\n"
        "tcp4       0      0  127.0.0.1.52906        *.*                    LISTEN\n"
        "tcp4       0      0  127.0.0.1.11434        127.0.0.1.60000        ESTABLISHED\n"
    )
    SS = (
        "LISTEN 0 4096 127.0.0.1:11434 0.0.0.0:*\n"
        "LISTEN 0 4096 [::]:11434 [::]:*\n"
        "LISTEN 0 4096 0.0.0.0:22 0.0.0.0:*\n"
    )

    def test_parse_netstat(self):
        self.assertEqual(sorted(mt.parse_netstat(self.NETSTAT, 11434)), ["*", "127.0.0.1"])
        self.assertEqual(mt.parse_netstat(self.NETSTAT, 9), [])

    def test_parse_ss(self):
        self.assertEqual(sorted(mt.parse_ss(self.SS, 11434)), ["127.0.0.1", "::"])

    def test_exposed_hosts(self):
        self.assertEqual(mt.exposed_hosts(["127.0.0.1", "::1"]), [])
        self.assertEqual(mt.exposed_hosts(["127.0.0.1", "*", "0.0.0.0"]), ["*", "0.0.0.0"])

    def test_unknown_listener_state_refuses(self):
        with mock.patch.object(mt, "listening_hosts", return_value=None):
            with self.assertRaises(mt.TaskError) as cm:
                mt.check_listener(11434)
        self.assertEqual(cm.exception.code, mt.EXIT_REFUSED)

    def test_exposed_listener_refuses(self):
        with mock.patch.object(mt, "listening_hosts", return_value=["127.0.0.1", "*"]):
            with self.assertRaises(mt.TaskError) as cm:
                mt.check_listener(11434)
        self.assertEqual(cm.exception.code, mt.EXIT_REFUSED)


class TestHelpers(unittest.TestCase):
    def test_schema(self):
        schema = {"summary": "string", "count": "number", "ok": "boolean", "items": "array", "meta": "object"}
        good = {"summary": "s", "count": 2, "ok": True, "items": [], "meta": {}, "extra": 1}
        self.assertEqual(mt.check_schema(good, schema), [])
        bad = {"summary": 3, "count": True, "items": {}, "meta": []}
        problems = mt.check_schema(bad, schema)
        self.assertEqual(len(problems), 5)  # 4 wrong types + missing "ok"

    def test_size_ctx(self):
        self.assertEqual(mt.size_ctx(100, 32768), 4096)
        self.assertEqual(mt.size_ctx(30000, 32768) % 1024, 0)
        self.assertGreater(mt.size_ctx(30000, 32768), 30000 // 3)
        with self.assertRaises(mt.TaskError):
            mt.size_ctx(200000, 32768)

    def test_truncation(self):
        self.assertFalse(mt.is_truncated(1000, 8192))
        self.assertTrue(mt.is_truncated(8190, 8192))
        self.assertFalse(mt.is_truncated(None, 8192))

    def test_parse_match(self):
        self.assertEqual(mt.parse_match("./a/b.py\x0012:  x = 1\n"), ("a/b.py", 12, "  x = 1"))
        self.assertEqual(mt.parse_match("a:1:b/.env\x003:TOKEN=x\n")[0], "a:1:b/.env")
        self.assertTrue(mt.is_hidden(mt.parse_match("a:1:b/.env\x003:TOKEN=x\n")[0]))
        self.assertIsNone(mt.parse_match("a/b.py:12:no nul separator\n"))
        self.assertIsNone(mt.parse_match("Binary file x matches\n"))

    def test_filter_hits(self):
        raw = [{"id": 2, "reason": "r2"}, {"id": 9, "reason": "invented"}, {"id": 2, "reason": "dup"},
               {"id": "1", "reason": "string id"}, {"reason": "no id"}]
        kept, dropped = mt.filter_hits(raw, 3)
        self.assertEqual([h["id"] for h in kept], [2])
        self.assertEqual(dropped, 4)

    def test_strip_fences(self):
        self.assertEqual(mt.strip_fences('```json\n{"a": 1}\n```'), '{"a": 1}')
        self.assertEqual(mt.strip_fences('{"a": 1}'), '{"a": 1}')

    def test_locate_quote(self):
        sources = [("a.log", "first line\n  second   line here\n"), ("b.log", "other\n")]
        self.assertEqual(mt.locate_quote("second line here", sources), "a.log:2")
        self.assertEqual(mt.locate_quote("other", sources), "b.log:1")
        self.assertIsNone(mt.locate_quote("not present anywhere", sources))
        self.assertIsNone(mt.locate_quote("ab", sources))
        self.assertIsNone(mt.locate_quote(None, sources))

    def test_redact(self):
        self.assertEqual(mt.redact("Bearer sk-123 failed", "sk-123"), "Bearer [redacted] failed")
        self.assertEqual(mt.redact("text", None), "text")


# ---------------------------------------------------------------- integration

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="model-task-test-"))
        self.state = self.tmp / "state"
        self.cfg = self.tmp / "config" / "backends.json"
        self.fake = None
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.env = dict(os.environ, LOCAL_MODEL_TASK_CONFIG=str(self.cfg), LOCAL_MODEL_TASK_STATE=str(self.state),
                        HOME=str(self.home))
        self.env.pop("MODEL_GATEWAY_KEY", None)

    def tearDown(self):
        if self.fake:
            self.fake.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def serve(self, **kw):
        self.fake = FakeBackend(**kw).start()
        return self.fake

    def write_config(self, backends, default=None):
        self.cfg.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.write_text(json.dumps({"default": default or next(iter(backends)), "backends": backends}))

    def main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=True), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = mt.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def cli(self, *argv, env=None):
        return subprocess.run([sys.executable, str(SCRIPT), *argv], env=env or self.env,
                              text=True, capture_output=True, timeout=60)

    def brief(self, text="Summarize the log."):
        p = self.tmp / "brief.md"
        p.write_text(text)
        return str(p)

    def runs(self):
        return sorted(d for d in self.state.iterdir() if d.is_dir() and d.name != "locks") if self.state.exists() else []


class TestRun(Base):
    def test_ollama_run_writes_output_and_report(self):
        fake = self.serve(reply="The log shows two errors.")
        self.write_config({"ollama": backend(fake.url)})
        log = self.tmp / "app.log"
        log.write_text("ERROR one\nINFO fine\nERROR two\n")
        code, out, err = self.main("run", "--brief", self.brief(), "--input", str(log), "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        self.assertIn("The log shows two errors.", out)
        post = fake.posts()[0]
        self.assertEqual(post["path"], "/api/chat")
        body = post["body"]
        self.assertEqual(body["keep_alive"], "1m")
        self.assertFalse(body["stream"])
        self.assertFalse(body["think"])
        self.assertGreaterEqual(body["options"]["num_ctx"], 4096)
        self.assertIn("ERROR two", body["messages"][-1]["content"])
        run = self.runs()[0]
        self.assertEqual((run / "output.md").read_text().strip(), "The log shows two errors.")
        report = json.loads((run / "report.json").read_text())
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(report["locality"], "local")
        self.assertTrue((run / "brief.md").exists())

    def unloads(self, fake):
        return [p for p in fake.posts() if p["path"] == "/api/generate"]

    def test_unloads_when_nothing_is_waiting(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        code, _, err = self.main("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        unloads = self.unloads(fake)
        self.assertEqual(len(unloads), 1)
        self.assertEqual(unloads[0]["body"], {"model": "qwen3.5:4b", "keep_alive": 0})
        self.assertEqual(fake.posts()[-1]["path"], "/api/generate")
        self.assertTrue(json.loads((self.runs()[0] / "report.json").read_text())["unloaded"])

    def test_stays_loaded_while_another_run_waits(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        with mock.patch.dict(os.environ, self.env, clear=True):
            waiting = mt.lock_path().parent / "waiting"
        waiting.mkdir(parents=True)
        (waiting / f"{os.getpid()}.abcd1234").touch()   # this test process is alive, so it counts
        code, _, err = self.main("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.unloads(fake), [])
        self.assertFalse(json.loads((self.runs()[0] / "report.json").read_text())["unloaded"])

    def test_stale_waiter_is_ignored(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        with mock.patch.dict(os.environ, self.env, clear=True):
            waiting = mt.lock_path().parent / "waiting"
        waiting.mkdir(parents=True)
        stale = waiting / "999999.deadbeef"
        stale.touch()
        with mock.patch.object(mt, "pid_alive", side_effect=lambda pid: pid != 999999):
            code, _, err = self.main("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.unloads(fake)), 1)
        self.assertFalse(stale.exists())

    def test_unloads_after_failures(self):
        for kw, expected in (({"status": 500}, mt.EXIT_BACKEND), ({"delay": 3}, mt.EXIT_TIMEOUT)):
            fake = self.serve(**kw)
            self.write_config({"ollama": backend(fake.url)})
            code, _, err = self.main("run", "--brief", self.brief(), "--timeout", "1", "--min-free-gb", "0")
            self.assertEqual(code, expected, err)
            self.assertEqual(len(self.unloads(fake)), 1, kw)
            fake.stop()
            self.fake = None

    def test_search_unloads_too(self):
        fake = self.serve(reply='{"answers_question": false, "hits": []}')
        self.write_config({"ollama": backend(fake.url)})
        root = self.tmp / "t"
        root.mkdir()
        (root / "a.py").write_text("X = 1\n")
        code, _, err = self.main("search", "--question", "q", "--pattern", "X", "--path", str(root),
                                 "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.unloads(fake)), 1)

    def test_private_ollama_backend_never_gets_an_unload_call(self):
        fake = self.serve()
        self.write_config({"tunnel": backend(fake.url, locality="private")})
        code, _, err = self.main("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.unloads(fake), [])

    def test_waiting_markers_are_parsed_strictly(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        with mock.patch.dict(os.environ, self.env, clear=True):
            waiting = mt.lock_path().parent / "waiting"
        waiting.mkdir(parents=True)
        odd = [waiting / "0.abcdef12", waiting / "12345678901234567890.abcdef12", waiting / "notes.txt"]
        for f in odd:
            f.touch()
        (waiting / "77.abcdef12").mkdir()            # a directory shaped like a marker
        old = waiting / f"{os.getpid()}.0123abcd"    # a live pid, but older than any run can wait
        old.touch()
        os.utime(old, (0, 0))
        code, _, err = self.main("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.unloads(fake)), 1)   # none of these counts as a waiting run
        self.assertTrue(all(f.exists() for f in odd))  # names that are not markers are left alone
        self.assertFalse(old.exists())                 # a stale marker is cleared

    def test_settle_never_raises(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        with mock.patch.object(mt.LocalLock, "others_waiting", side_effect=OSError("boom")):
            code, _, err = self.main("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        report = json.loads((self.runs()[0] / "report.json").read_text())
        self.assertIn("boom", report.get("unload_error", ""))

    def test_openai_backend_never_gets_an_unload_call(self):
        fake = self.serve()
        self.write_config({"v1": backend(fake.url + "/v1", api="openai")})
        code, _, err = self.main("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.unloads(fake), [])

    def test_cloud_model_refused_before_any_request(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        code, _, err = self.main("run", "--brief", self.brief(), "--model", "kimi-k2.6:cloud", "--min-free-gb", "0")
        self.assertEqual(code, mt.EXIT_REFUSED, err)
        self.assertEqual(fake.requests, [])

    def test_hosted_needs_flag(self):
        self.write_config({"hosted": backend("https://hosted.invalid/v1", api="openai", locality="hosted")})
        code, _, err = self.main("run", "--brief", self.brief())
        self.assertEqual(code, mt.EXIT_REFUSED, err)
        self.assertIn("--allow-hosted", err)

    def test_local_off_loopback_config_refused(self):
        self.write_config({"ollama": backend("http://192.168.1.5:11434")})
        code, _, _ = self.main("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(code, mt.EXIT_REFUSED)

    def test_schema_pass_and_fail(self):
        fake = self.serve(reply='```json\n{"summary": "two errors", "count": 2}\n```')
        self.write_config({"ollama": backend(fake.url)})
        schema = self.tmp / "schema.json"
        schema.write_text(json.dumps({"summary": "string", "count": "number"}))
        code, out, err = self.main("run", "--brief", self.brief(), "--schema", str(schema), "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        self.assertEqual(fake.posts()[0]["body"]["format"], "json")
        result = json.loads((self.runs()[0] / "result.json").read_text())
        self.assertEqual(result["count"], 2)

        fake.reply = '{"summary": 5}'
        code, _, err = self.main("run", "--brief", self.brief(), "--schema", str(schema), "--min-free-gb", "0")
        self.assertEqual(code, mt.EXIT_SCHEMA, err)
        self.assertTrue(any((r / "raw_output.md").exists() for r in self.runs()))

    def test_schema_evidence_is_verified_against_inputs(self):
        reply = json.dumps({"status": "failed", "first_test": "test_refund", "recovered": False,
                            "evidence": {"status": "pipeline   status=failed", "first_test": "made-up quote here",
                                         "recovered": "ok"}})
        fake = self.serve(reply=reply)
        self.write_config({"ollama": backend(fake.url)})
        log = self.tmp / "app.log"
        log.write_text("step=test first_failure=test_refund\nbuild status=ok\npipeline status=failed\n")
        schema = self.tmp / "schema.json"
        schema.write_text(json.dumps({"status": "string", "first_test": "string", "recovered": "boolean"}))
        code, out, err = self.main("run", "--brief", self.brief(), "--input", str(log), "--schema", str(schema),
                                   "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        self.assertEqual(fake.posts()[0]["body"]["options"]["temperature"], 0)
        self.assertIn('"evidence"', fake.posts()[0]["body"]["messages"][-1]["content"])
        run = self.runs()[0]
        self.assertNotIn("evidence", json.loads((run / "result.json").read_text()))
        evidence = json.loads((run / "evidence.json").read_text())
        self.assertEqual(evidence["status"]["location"], f"{log}:3")
        self.assertFalse(evidence["first_test"]["supported"])
        self.assertFalse(evidence["recovered"]["supported"])  # too short to count as evidence
        self.assertIn(f'[{log}:3] "pipeline   status=failed"', out)
        self.assertIn("unsupported", out)
        self.assertIn("1 of 3 fields quote a line", out)
        self.assertIn("not that the value is right", out)

    def test_schema_may_not_use_reserved_key(self):
        schema = self.tmp / "schema.json"
        schema.write_text(json.dumps({"evidence": "string"}))
        self.write_config({"ollama": backend("http://127.0.0.1:11434")})
        code, _, _ = self.main("run", "--brief", self.brief(), "--schema", str(schema), "--min-free-gb", "0")
        self.assertEqual(code, mt.EXIT_ARGS)

    def test_timeout(self):
        fake = self.serve(delay=3)
        self.write_config({"ollama": backend(fake.url)})
        code, _, err = self.main("run", "--brief", self.brief(), "--timeout", "1", "--min-free-gb", "0")
        self.assertEqual(code, mt.EXIT_TIMEOUT, err)

    def test_truncated_prompt(self):
        fake = self.serve(prompt_eval_count=4096)
        self.write_config({"ollama": backend(fake.url)})
        code, _, err = self.main("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(code, mt.EXIT_BACKEND, err)
        self.assertIn("cut part of it", err)

    def test_backend_http_error(self):
        fake = self.serve(status=500)
        self.write_config({"ollama": backend(fake.url)})
        code, _, _ = self.main("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(code, mt.EXIT_BACKEND)

    def test_memory_floor(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        with mock.patch.object(mt, "free_memory_bytes", return_value=1 << 30):
            code, _, err = self.main("run", "--brief", self.brief(), "--min-free-gb", "4")
        self.assertEqual(code, mt.EXIT_ARGS)
        self.assertIn("free", err)
        self.assertEqual(fake.requests, [])

    def test_input_caps(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        big = self.tmp / "big.txt"
        big.write_text("x" * 3000)
        code, _, _ = self.main("run", "--brief", self.brief(), "--input", str(big), "--max-input-kb", "1",
                               "--min-free-gb", "0")
        self.assertEqual(code, mt.EXIT_ARGS)
        binary = self.tmp / "bin.dat"
        binary.write_bytes(b"\x00\x01\x02")
        code, _, _ = self.main("run", "--brief", self.brief(), "--input", str(binary), "--min-free-gb", "0")
        self.assertEqual(code, mt.EXIT_ARGS)
        self.assertEqual(fake.requests, [])

    def test_openai_private_backend_and_key_never_leaks(self):
        secret = "sk-test-secret-123"
        fake = self.serve(status=500, error_body=lambda h: json.dumps({"error": f"bad auth {h.get('Authorization')}"}))
        self.write_config({"gw": backend(fake.url + "/v1", api="openai", locality="private", model="small",
                                         api_key_env="MODEL_GATEWAY_KEY")})
        self.env["MODEL_GATEWAY_KEY"] = secret
        code, out, err = self.main("run", "--brief", self.brief())
        self.assertEqual(code, mt.EXIT_BACKEND)
        self.assertEqual(fake.posts()[0]["path"], "/v1/chat/completions")
        self.assertEqual(fake.posts()[0]["headers"].get("Authorization"), f"Bearer {secret}")
        self.assertNotIn(secret, out + err)
        for f in self.runs()[0].iterdir():
            self.assertNotIn(secret, f.read_text(), f.name)

    def test_key_with_control_characters_refused_without_echo(self):
        secret = "sk-test-secret-456"
        self.write_config({"gw": backend("http://127.0.0.1:9/v1", api="openai", locality="private",
                                         api_key_env="MODEL_GATEWAY_KEY")})
        self.env["MODEL_GATEWAY_KEY"] = secret + "\n"
        code, out, err = self.main("run", "--brief", self.brief())
        self.assertEqual(code, mt.EXIT_ARGS)
        self.assertIn("MODEL_GATEWAY_KEY", err)
        self.assertNotIn(secret, out + err)

    def test_remote_alias_refused_before_any_post(self):
        fake = self.serve(models=("qwen3.5:4b", {"name": "kimi-alias:latest", "remote_host": "https://ollama.com:443",
                                                 "remote_model": "kimi-k2.6"}))
        self.write_config({"ollama": backend(fake.url)})
        code, _, err = self.main("run", "--brief", self.brief(), "--model", "kimi-alias", "--min-free-gb", "0")
        self.assertEqual(code, mt.EXIT_REFUSED, err)
        self.assertIn("ollama.com", err)
        self.assertEqual(fake.posts(), [])

    def test_remote_alias_refused_through_openai_route_to_ollama(self):
        fake = self.serve(models=("qwen3.5:4b", {"name": "kimi-alias:latest", "remote_host": "https://ollama.com:443"}))
        self.write_config({"v1": backend(fake.url + "/v1", api="openai", model="kimi-alias")})
        code, _, err = self.main("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(code, mt.EXIT_REFUSED, err)
        self.assertEqual(fake.posts(), [])
        self.write_config({"v1": backend(fake.url + "/v1", api="openai", model="qwen3.5:4b")})
        code, _, err = self.main("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        self.assertEqual(fake.posts()[0]["path"], "/v1/chat/completions")

    def test_model_not_installed(self):
        fake = self.serve(models=("qwen3.5:4b",))
        self.write_config({"ollama": backend(fake.url)})
        code, _, err = self.main("run", "--brief", self.brief(), "--model", "nope:1b", "--min-free-gb", "0")
        self.assertEqual(code, mt.EXIT_ARGS, err)
        self.assertIn("ollama pull", err)
        self.assertEqual(fake.posts(), [])

    def test_prune_removes_only_old_run_dirs(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        self.state.mkdir(parents=True)
        old_run = self.state / "20200101-000000-abcdef"
        keep = self.state / "not-a-run"
        for d in (old_run, keep):
            d.mkdir()
            os.utime(d, (0, 0))
        code, _, err = self.main("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        self.assertFalse(old_run.exists())
        self.assertTrue(keep.exists())

    def test_missing_key_env(self):
        self.write_config({"gw": backend("http://127.0.0.1:9/v1", api="openai", locality="private",
                                         api_key_env="MODEL_GATEWAY_KEY")})
        code, _, err = self.main("run", "--brief", self.brief())
        self.assertEqual(code, mt.EXIT_ARGS)
        self.assertIn("MODEL_GATEWAY_KEY", err)


class TestSearch(Base):
    def make_tree(self):
        root = self.tmp / "tree"
        (root / "pkg").mkdir(parents=True)
        (root / "pkg" / "env.py").write_text("ENV_ALLOW = ('HOME', 'PATH')\n")
        (root / "pkg" / "use.py").write_text("from env import ENV_ALLOW\nprint(ENV_ALLOW)\n")
        return root

    def test_search_keeps_only_sent_matches(self):
        def choose(body):
            prompt = body["messages"][-1]["content"]
            # pick the match whose text defines the name, plus one invented id
            ids = [line.split("]")[0].lstrip("[") for line in prompt.splitlines()
                   if line.startswith("[") and "ENV_ALLOW =" in line]
            return json.dumps({"hits": [{"id": int(ids[0]), "reason": "defines it"},
                                        {"id": 999, "reason": "invented"}]})
        fake = self.serve(reply=choose)
        self.write_config({"ollama": backend(fake.url)})
        root = self.make_tree()
        code, out, err = self.main("search", "--question", "Where is ENV_ALLOW defined?",
                                   "--pattern", "ENV_ALLOW", "--path", str(root), "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        self.assertIn("env.py:1", out)
        report = json.loads((self.runs()[0] / "report.json").read_text())
        self.assertEqual(report["hits_kept"], 1)
        self.assertEqual(report["hits_dropped"], 1)
        self.assertEqual(report["matches_sent"], 3)
        self.assertFalse(report["matches_capped"])
        self.assertEqual(fake.posts()[0]["body"]["options"]["temperature"], 0)

    def test_search_cap_reported(self):
        fake = self.serve(reply='{"hits": []}')
        self.write_config({"ollama": backend(fake.url)})
        root = self.make_tree()
        code, out, err = self.main("search", "--question", "q", "--pattern", "ENV_ALLOW", "--path", str(root),
                                   "--max-matches", "1", "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        self.assertIn("not that the target is absent", out)
        report = json.loads((self.runs()[0] / "report.json").read_text())
        self.assertTrue(report["matches_capped"])

    def test_no_matches_skips_model(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        code, out, _ = self.main("search", "--question", "q", "--pattern", "NOTHING_HERE_XYZ",
                                 "--path", str(self.make_tree()), "--min-free-gb", "0")
        self.assertEqual(code, 0)
        self.assertEqual(fake.posts(), [])
        self.assertIn("no matches", out.lower())

    def test_search_model_says_nothing_answers(self):
        fake = self.serve(reply='{"answers_question": false, "hits": [{"id": 1, "reason": "shares a word"}]}')
        self.write_config({"ollama": backend(fake.url)})
        code, out, err = self.main("search", "--question", "Where is the pool configured?", "--pattern", "ENV_ALLOW",
                                   "--path", str(self.make_tree()), "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        report = json.loads((self.runs()[0] / "report.json").read_text())
        self.assertEqual((report["hits_kept"], report["hits_dropped"]), (0, 1))
        self.assertIn("No hits.", out)

    def test_grep_fallback_skips_hidden_files(self):
        fake = self.serve(reply='{"answers_question": false, "hits": []}')
        self.write_config({"ollama": backend(fake.url)})
        root = self.make_tree()
        (root / ".env").write_text("ENV_ALLOW_TOKEN=supersecretvalue\n")
        (root / ".hidden").mkdir()
        (root / ".hidden" / "x.py").write_text("ENV_ALLOW = 'hidden copy'\n")
        (root / "a:1:b").mkdir()
        (root / "a:1:b" / ".npmrc").write_text("ENV_ALLOW_KEY=colondirsecret\n")
        real_which = shutil.which
        with mock.patch.object(mt.shutil, "which", side_effect=lambda n: None if n == "rg" else real_which(n)):
            code, _, err = self.main("search", "--question", "q", "--pattern", "ENV_ALLOW", "--path", str(root),
                                     "--min-free-gb", "0")
        self.assertEqual(code, 0, err)
        prompt = fake.posts()[0]["body"]["messages"][-1]["content"]
        self.assertNotIn("supersecretvalue", prompt)
        self.assertNotIn("hidden copy", prompt)
        self.assertNotIn("colondirsecret", prompt)
        self.assertIn("env.py", prompt)

    def test_search_bad_json(self):
        fake = self.serve(reply="not json at all")
        self.write_config({"ollama": backend(fake.url)})
        code, _, _ = self.main("search", "--question", "q", "--pattern", "ENV_ALLOW",
                               "--path", str(self.make_tree()), "--min-free-gb", "0")
        self.assertEqual(code, mt.EXIT_SCHEMA)


class TestListUseDoctor(Base):
    def test_list(self):
        fake = self.serve(models=("qwen3.5:4b", "qwen3:4b", "kimi-k2.6:cloud"))
        self.write_config({"ollama": backend(fake.url)})
        code, out, err = self.main("list")
        self.assertEqual(code, 0, err)
        self.assertIn("qwen3:4b", out)
        self.assertRegex(out, r"kimi-k2\.6:cloud.*refused")

    def test_list_skips_hosted_without_flag(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url),
                           "hosted": backend("https://hosted.invalid/v1", api="openai", locality="hosted")})
        code, out, err = self.main("list")
        self.assertEqual(code, 0, err)
        self.assertRegex(out, r"hosted:.*\n\s+skipped")

    def test_list_marks_remote_alias(self):
        fake = self.serve(models=({"name": "kimi-alias:latest", "remote_host": "https://ollama.com:443"},))
        self.write_config({"ollama": backend(fake.url)})
        code, out, _ = self.main("list")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"kimi-alias:latest.*refused")

    def test_use_sets_default_and_is_idempotent(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        code, _, err = self.main("use", "ollama/qwen3:4b")
        self.assertEqual(code, 0, err)
        first = self.cfg.read_bytes()
        self.assertEqual(json.loads(first)["backends"]["ollama"]["default_model"], "qwen3:4b")
        self.main("use", "ollama/qwen3:4b")
        self.assertEqual(self.cfg.read_bytes(), first)
        self.assertEqual(oct(self.cfg.stat().st_mode & 0o777), "0o600")

    def test_use_refuses_cloud_and_unknown(self):
        self.write_config({"ollama": backend("http://127.0.0.1:11434")})
        self.assertEqual(self.main("use", "ollama/kimi-k2.6:cloud")[0], mt.EXIT_REFUSED)
        self.assertEqual(self.main("use", "nope/model")[0], mt.EXIT_ARGS)

    def test_use_without_config_starts_from_defaults(self):
        code, _, err = self.main("use", "ollama/qwen3:4b")
        self.assertEqual(code, 0, err)
        cfg = json.loads(self.cfg.read_text())
        self.assertEqual(cfg["backends"]["ollama"]["base_url"], "http://127.0.0.1:11434")

    def doctor_with_app_env(self, values):
        with mock.patch.object(mt, "app_env", side_effect=lambda name: values.get(name)):
            return self.main("doctor")

    def test_doctor(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        self.env.pop("OLLAMA_HOST", None)
        settled = {"OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_NUM_PARALLEL": "1"}
        code, out, err = self.doctor_with_app_env(settled)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("warn", out)
        self.env["OLLAMA_HOST"] = "0.0.0.0:11434"
        code, out, _ = self.doctor_with_app_env(settled)
        self.assertEqual(code, 1)
        self.assertIn("OLLAMA_HOST", out)

    def test_doctor_reads_the_ollama_app_settings(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        self.env.pop("OLLAMA_HOST", None)
        code, out, _ = self.doctor_with_app_env({"OLLAMA_HOST": "0.0.0.0:11434", "OLLAMA_MAX_LOADED_MODELS": "1"})
        self.assertEqual(code, 1)
        self.assertRegex(out, r"FAIL.*Ollama app.*OLLAMA_HOST")

    @unittest.skipUnless(sys.platform == "darwin", "the Ollama app settings are read through launchctl")
    def test_doctor_warns_when_several_models_can_load(self):
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        self.env.pop("OLLAMA_HOST", None)
        code, out, _ = self.doctor_with_app_env({})
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"warn.*OLLAMA_MAX_LOADED_MODELS")


class TestLock(Base):
    def test_lock_path_ignores_state_dir(self):
        with mock.patch.dict(os.environ, dict(self.env, LOCAL_MODEL_TASK_STATE=str(self.tmp / "a")), clear=True):
            first = mt.lock_path()
        with mock.patch.dict(os.environ, dict(self.env, LOCAL_MODEL_TASK_STATE=str(self.tmp / "b")), clear=True):
            second = mt.lock_path()
        self.assertEqual(first, second)
        self.assertTrue(str(first).startswith(str(self.home)))

    def test_local_run_waits_for_the_lock_then_times_out(self):
        import fcntl
        fake = self.serve()
        self.write_config({"ollama": backend(fake.url)})
        with mock.patch.dict(os.environ, self.env, clear=True):
            path = mt.lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            code, _, err = self.main("run", "--brief", self.brief(), "--timeout", "1", "--min-free-gb", "0")
        finally:
            os.close(fd)
        self.assertEqual(code, mt.EXIT_TIMEOUT, err)
        self.assertIn("another local run", err)
        self.assertEqual(fake.posts(), [])


# ---------------------------------------------------------------- end to end

class TestCli(Base):
    def test_cli_run_end_to_end(self):
        fake = self.serve(reply="done")
        self.write_config({"ollama": backend(fake.url)})
        proc = self.cli("run", "--brief", self.brief(), "--min-free-gb", "0")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("done", proc.stdout)
        self.assertEqual(len(self.runs()), 1)

    def test_cli_brief_from_stdin(self):
        fake = self.serve(reply="from stdin")
        self.write_config({"ollama": backend(fake.url)})
        proc = subprocess.run([sys.executable, str(SCRIPT), "run", "--brief", "-", "--min-free-gb", "0"],
                              input="Say hi.", env=self.env, text=True, capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Say hi.", fake.posts()[0]["body"]["messages"][-1]["content"])

    def test_cli_sigterm_still_unloads(self):
        import signal
        import time
        fake = self.serve(delay=5)
        self.write_config({"ollama": backend(fake.url)})
        proc = subprocess.Popen([sys.executable, str(SCRIPT), "run", "--brief", self.brief(), "--min-free-gb", "0"],
                                env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 20
        while not any(p["path"] == "/api/chat" for p in fake.posts()) and time.monotonic() < deadline:
            time.sleep(0.1)
        proc.send_signal(signal.SIGTERM)
        _, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 130, err)
        self.assertEqual([p["path"] for p in fake.posts()], ["/api/chat", "/api/generate"])
        report = json.loads((self.runs()[0] / "report.json").read_text())
        self.assertEqual(report["exit_code"], 130)
        self.assertTrue(report["unloaded"])

    def test_cli_bad_args(self):
        self.assertEqual(self.cli("run").returncode, mt.EXIT_ARGS)
        self.assertEqual(self.cli("run", "--brief", self.brief(), "--timeout", "99999").returncode, mt.EXIT_ARGS)


if __name__ == "__main__":
    unittest.main()
