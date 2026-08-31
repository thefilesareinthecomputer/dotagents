#!/usr/bin/env python3
"""Tests for skills/cover-me/scripts/distil_transcript.py.

Stdlib unittest, synthetic fixtures only. No real transcript content is read
or committed here; every event below is fabricated.

Run: python3 -m unittest discover -s skills/cover-me/tests -v
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
)

import distil_transcript as dt  # noqa: E402


def user_text(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def assistant_text(text):
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def tool_call(name, tool_input):
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": name, "input": tool_input}
            ],
        },
    }


def tool_result(text, is_error=False):
    block = {"type": "tool_result", "tool_use_id": "t1", "content": text}
    if is_error:
        block["is_error"] = True
    return {"type": "user", "message": {"role": "user", "content": [block]}}


def lines(events):
    return [json.dumps(e) + "\n" for e in events]


class TestProjection(unittest.TestCase):
    def test_roles_kinds_and_order(self):
        out = dt.distil(
            lines(
                [
                    user_text("do the thing"),
                    assistant_text("on it"),
                    tool_call("Bash", {"command": "ls"}),
                    tool_result("a\nb"),
                ]
            )
        )
        self.assertIn("[#1 user text]\ndo the thing\n", out)
        self.assertIn("[#2 assistant text]\non it\n", out)
        self.assertIn('[#3 assistant tool_call]\nBash {"command": "ls"}\n', out)
        self.assertIn("[#4 user tool_result]\na\nb\n", out)
        self.assertLess(out.index("[#1 "), out.index("[#4 "))
        self.assertIn("# parts 1-4 of 4 (cap 500 chars/part)", out)

    def test_thinking_projects_as_text(self):
        event = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "thinking", "thinking": "hmm"}],
            },
        }
        self.assertIn("[#1 assistant text]\nhmm\n", dt.distil(lines([event])))

    def test_error_tool_result_is_marked(self):
        out = dt.distil(lines([tool_result("boom", is_error=True)]))
        self.assertIn("[#1 user tool_result]\n[error] boom\n", out)

    def test_multiple_blocks_become_separate_parts(self):
        event = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "first"},
                    {"type": "tool_use", "id": "t", "name": "Read", "input": {}},
                ],
            },
        }
        out = dt.distil(lines([event]))
        self.assertIn("[#1 assistant text]", out)
        self.assertIn("[#2 assistant tool_call]", out)

    def test_window_keeps_the_last_n(self):
        out = dt.distil(lines([user_text("m%d" % i) for i in range(10)]), n=3)
        self.assertIn("# parts 8-10 of 10", out)
        self.assertNotIn("m6", out)
        self.assertIn("m9", out)


class TestCapping(unittest.TestCase):
    def test_part_body_capped_with_marker(self):
        out = dt.distil(lines([user_text("x" * 1200)]), cap=500)
        body = out.split("[#1 user text]\n", 1)[1].rstrip("\n")
        head, marker = body.split(" ...[", 1)
        self.assertEqual(len(head), 500)
        self.assertEqual(marker, "+700 chars]")

    def test_short_part_is_untouched(self):
        out = dt.distil(lines([user_text("short")]), cap=500)
        self.assertIn("[#1 user text]\nshort\n", out)
        self.assertNotIn("...[+", out)

    def test_single_oversized_line_is_capped_not_dropped(self):
        # ~300KB tool result, the measured worst case for a real transcript.
        payload = "z" * 300000
        events = lines([user_text("before"), tool_result(payload), user_text("after")])
        self.assertGreater(len(events[1]), 290000)
        out = dt.distil(events, cap=500)
        self.assertIn("[#2 user tool_result]", out)
        self.assertIn("...[+299500 chars]", out)
        self.assertLess(len(out), 2000)


class TestNoiseSkipping(unittest.TestCase):
    def test_all_seven_noise_types_skipped(self):
        noise = [{"type": t, "sessionId": "s"} for t in sorted(dt.NOISE_TYPES)]
        self.assertEqual(len(noise), 7)
        out = dt.distil(lines(noise + [user_text("signal")]))
        self.assertIn("# parts 1-1 of 1", out)
        self.assertIn("signal", out)
        for t in dt.NOISE_TYPES:
            self.assertNotIn(t, out)

    def test_unknown_types_skipped(self):
        events = [
            {"type": "system", "subtype": "x"},
            {"type": "file-history-delta", "backup": "y"},
            {"type": "brand-new-2027", "whatever": 1},
            user_text("signal"),
        ]
        out = dt.distil(lines(events))
        self.assertIn("# parts 1-1 of 1", out)
        self.assertNotIn("brand-new-2027", out)


class TestByteCeiling(unittest.TestCase):
    def test_truncates_oldest_first_and_reports(self):
        events = lines([user_text("part%03d " % i + "q" * 400) for i in range(50)])
        out = dt.distil(events, cap=500, max_bytes=3000)
        self.assertLessEqual(len(out.encode("utf-8")), 3000)
        self.assertIn("# byte ceiling 3000: dropped", out)
        self.assertNotIn("part000", out)
        self.assertIn("part049", out)

    def test_ordinals_survive_truncation(self):
        events = lines([user_text("m%d " % i + "q" * 400) for i in range(50)])
        out = dt.distil(events, cap=500, max_bytes=3000)
        self.assertIn("# parts 4", out[: out.index("\n\n")])
        kept = [l for l in out.splitlines() if l.startswith("[#")]
        self.assertEqual(kept[-1], "[#50 user text]")

    def test_ceiling_below_one_part_drops_everything_and_says_so(self):
        # The ceiling is hard: only the header survives, and it reports the drop.
        out = dt.distil(lines([user_text("q" * 400)]), cap=500, max_bytes=10)
        self.assertNotIn("[#", out)
        self.assertIn("# byte ceiling 10: dropped 1 oldest parts", out)


class TestRobustness(unittest.TestCase):
    def test_malformed_final_line_is_skipped_not_fatal(self):
        good = lines([user_text("alpha"), user_text("beta")])
        truncated = json.dumps(user_text("gamma"))[:40]
        out = dt.distil(good + [truncated])
        self.assertIn("alpha", out)
        self.assertIn("beta", out)
        self.assertIn("# skipped 1 malformed lines", out)
        self.assertIn("# parts 1-2 of 2", out)

    def test_malformed_line_in_the_middle(self):
        good = lines([user_text("alpha")])
        out = dt.distil(good + ["{not json at all\n"] + lines([user_text("beta")]))
        self.assertIn("alpha", out)
        self.assertIn("beta", out)
        self.assertIn("# skipped 1 malformed lines", out)

    def test_non_object_json_line_is_malformed(self):
        out = dt.distil(["[1,2,3]\n"] + lines([user_text("alpha")]))
        self.assertIn("# skipped 1 malformed lines", out)
        self.assertIn("alpha", out)

    def test_empty_file(self):
        out = dt.distil([])
        self.assertIn("# no parts (cap 500 chars/part)", out)
        self.assertNotIn("[#", out)

    def test_blank_lines_only(self):
        out = dt.distil(["\n", "   \n", "\n"])
        self.assertIn("# no parts", out)
        self.assertNotIn("skipped", out)

    def test_missing_message_or_content(self):
        events = [
            {"type": "user"},
            {"type": "assistant", "message": {"content": None}},
            {"type": "assistant", "message": {"content": ["raw string"]}},
            user_text("signal"),
        ]
        out = dt.distil(lines(events))
        self.assertIn("# parts 1-1 of 1", out)


class TestPathDerivation(unittest.TestCase):
    def test_sanitize_cwd(self):
        self.assertEqual(dt.sanitize_cwd("/home/x/.agents"), "-home-x--agents")
        self.assertEqual(dt.sanitize_cwd("/a/b.c/d"), "-a-b-c-d")

    def test_project_dir(self):
        self.assertEqual(
            dt.project_dir(cwd="/w/proj", home="/h"),
            os.path.join("/h", ".claude", "projects", "-w-proj"),
        )

    def test_positional_path_wins(self):
        self.assertEqual(dt.resolve_transcript("/tmp/x.jsonl", "sid"), "/tmp/x.jsonl")

    def test_session_id_builds_the_path(self):
        self.assertEqual(
            dt.resolve_transcript(None, "sid-1", cwd="/w/proj", home="/h"),
            os.path.join("/h", ".claude", "projects", "-w-proj", "sid-1.jsonl"),
        )

    def test_newest_jsonl_fallback(self):
        with tempfile.TemporaryDirectory() as home:
            proj = os.path.join(home, ".claude", "projects", "-w-proj")
            os.makedirs(proj)
            old = os.path.join(proj, "old.jsonl")
            new = os.path.join(proj, "new.jsonl")
            for path, mtime in ((old, 1000), (new, 2000)):
                with open(path, "w") as handle:
                    handle.write("")
                os.utime(path, (mtime, mtime))
            with open(os.path.join(proj, "ignore.txt"), "w") as handle:
                handle.write("")
            self.assertEqual(dt.resolve_transcript(cwd="/w/proj", home=home), new)

    def test_missing_project_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertIsNone(dt.resolve_transcript(cwd="/w/proj", home=home))


class TestCli(unittest.TestCase):
    def test_missing_file_exits_nonzero_without_traceback(self):
        self.assertEqual(dt.main(["/no/such/transcript.jsonl"]), 2)


if __name__ == "__main__":
    unittest.main()
