"""Tests for hooks/reject_words.py: list loading and matching against an
invented list, the shipped list's shape, then the script run the way the
harness runs it, payload on stdin, with state and list redirected to a temp dir.
Target: the repo's hooks/reject_words.py by default; HOOK_UNDER_TEST points the run at a
station copy such as ~/.claude/hooks/reject_words.py (seeded per SPEC-CLAUDE-CODE.md §8).
Run: python3 tests/station-hooks/test-reject-words.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOK = Path(os.environ.get("HOOK_UNDER_TEST") or Path(__file__).resolve().parents[2] / "hooks" / "reject_words.py")
SHIPPED = HOOK.with_name("reject-words.toml")
spec = importlib.util.spec_from_file_location("reject_words", HOOK)
rw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rw)

LIST = """
[filler]
words = ["frobnicate", "deep dive"]
why = "Filler."
instead = "Say what happened."
ask = "is this a literal frob?"

[plain]
words = ["widgetry"]
why = "Vague."
instead = "Name the widget."

[broken]
words = "not a list"

[exempt]
tags = ["verbatim"]
"""


class Loading(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "list.toml"
        self.path.write_text(LIST)
        self.cats = rw.load_categories(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_skips_a_category_without_a_word_list(self):
        self.assertEqual([c[0] for c in self.cats], ["filler", "plain"])

    def test_missing_or_garbage_list_loads_nothing(self):
        self.assertEqual(rw.load_categories(Path(self.tmp.name) / "none.toml"), [])
        self.path.write_text("[[[ not toml")
        self.assertEqual(rw.load_categories(self.path), [])

    def test_python_without_tomllib_loads_nothing(self):
        with mock.patch.dict(sys.modules, {"tomllib": None}):
            self.assertEqual(rw.load_categories(self.path), [])

    def test_counts_words_and_phrases_by_category(self):
        got = rw.hits("We Frobnicate, then a deep\n dive into widgetry.", self.cats)
        self.assertEqual(got, {("filler", "frobnicate"): 1, ("filler", "deep dive"): 1,
                               ("plain", "widgetry"): 1})

    def test_ignores_joined_and_named_words(self):
        text = 'no-frobnicate-slug frobnicate_id `widgetry` "deep dive"\n```\nfrobnicate\n```\n'
        self.assertEqual(rw.hits(text, self.cats), {})

    def test_reason_steers_with_why_instead_and_ask(self):
        added = {("filler", "frobnicate"): 1, ("plain", "widgetry"): 1}
        text = rw.reason(added, self.cats, "doc.md")
        for part in ('"frobnicate" [filler]', "Why: Filler.", "Instead: Say what happened.",
                     "is this a literal frob?", '"widgetry" [plain]', "Instead: Name the widget.",
                     "resubmit the same write unchanged"):
            self.assertIn(part, text)


class ShippedList(unittest.TestCase):
    def test_every_category_has_words_why_and_instead(self):
        cats = rw.load_categories(SHIPPED)
        self.assertTrue(cats)
        for name, _, spec in cats:
            self.assertTrue(spec.get("why") and spec.get("instead"), name)


class Hook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "list.toml").write_text(LIST)
        self.env = dict(os.environ, XDG_STATE_HOME=str(self.root / "state"),
                        REJECT_WORDS_FILE=str(self.root / "list.toml"))

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, tool_input, session="s1", env=None):
        payload = {"session_id": session, "tool_name": "Write", "tool_input": tool_input}
        out = subprocess.run(
            ["python3", str(HOOK)], input=json.dumps(payload),
            capture_output=True, text=True, env=env or self.env, timeout=10,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout) if out.stdout.strip() else None

    def doc(self, name="doc.md"):
        return str(self.root / name)

    def test_doc_write_with_new_word_is_denied(self):
        res = self.run_hook({"file_path": self.doc(), "content": "We frobnicate."})
        self.assertEqual(res["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_doc_suffixes_in_any_case_are_checked(self):
        for name in ("a.MD", "a.txt", "a.rst", "a.mdx"):
            self.assertIsNotNone(self.run_hook({"file_path": self.doc(name), "content": "frobnicate"}), name)

    def test_code_files_are_not_checked(self):
        for name in ("a.py", "a.sql", "a.json"):
            self.assertIsNone(self.run_hook({"file_path": self.doc(name), "content": "frobnicate"}), name)

    def test_identical_retry_is_allowed_once(self):
        ti = {"file_path": self.doc(), "content": "A literal frobnicate."}
        self.assertIsNotNone(self.run_hook(ti))
        self.assertIsNone(self.run_hook(ti))
        self.assertIsNotNone(self.run_hook(ti))

    def test_keeping_an_existing_word_is_allowed(self):
        path = self.root / "old.md"
        path.write_text("We frobnicate.\n")
        self.assertIsNone(self.run_hook({"file_path": str(path), "content": "We frobnicate.\nMore.\n"}))
        ti = {"file_path": self.doc(), "old_string": "frobnicate", "new_string": "frobnicate it"}
        self.assertIsNone(self.run_hook(ti))

    def test_edit_and_multiedit_adding_a_word_are_denied(self):
        self.assertIsNotNone(self.run_hook({"file_path": self.doc(), "old_string": "a", "new_string": "widgetry"}))
        ti = {"file_path": self.doc(), "edits": [{"old_string": "a", "new_string": "b"},
                                                  {"old_string": "c", "new_string": "deep dive"}]}
        self.assertIsNotNone(self.run_hook(ti))

    def test_exempt_paths_are_untouched(self):
        self.assertIsNone(self.run_hook({"file_path": "/x/.claude/hooks/y.md", "content": "frobnicate"}))

    def test_verbatim_tag_in_frontmatter_exempts_a_write(self):
        for fm in ("tags: [quote, verbatim]", "tags: verbatim", "tags:\n  - quote\n  - verbatim", "tags: [\"Verbatim\"]"):
            res = self.run_hook({"file_path": self.doc(), "content": f"---\n{fm}\n---\n\nSeneca would frobnicate.\n"})
            self.assertIsNone(res, fm)

    def test_verbatim_tag_exempts_an_edit_to_a_tagged_file(self):
        path = self.root / "seneca.md"
        path.write_text("---\ntags:\n  - verbatim\n---\n\nText.\n")
        self.assertIsNone(self.run_hook({"file_path": str(path), "old_string": "Text.", "new_string": "We frobnicate."}))

    def test_tag_added_to_an_existing_authored_file_does_not_exempt(self):
        path = self.root / "essay.md"
        path.write_text("---\ntags: [draft]\n---\n\nText.\n")
        res = self.run_hook({"file_path": str(path), "content": "---\ntags: [draft, verbatim]\n---\n\nWe frobnicate.\n"})
        self.assertIsNotNone(res)

    def test_tag_outside_frontmatter_does_not_exempt(self):
        for body in ("tags: [verbatim]\n\nfrobnicate", "---\ntype: verbatim\n---\nfrobnicate",
                     "---\ntags: [quote]\n---\n\ntags: [verbatim]\nfrobnicate", "Intro.\n---\ntags: [verbatim]\n---\nfrobnicate"):
            self.assertIsNotNone(self.run_hook({"file_path": self.doc(), "content": body}), body)

    def test_no_exempt_table_means_no_exemption(self):
        lst = self.root / "noexempt.toml"
        lst.write_text(LIST.split("[exempt]")[0])
        env = dict(self.env, REJECT_WORDS_FILE=str(lst))
        res = self.run_hook({"file_path": self.doc(), "content": "---\ntags: [verbatim]\n---\nfrobnicate"}, env=env)
        self.assertIsNotNone(res)

    def test_frontmatter_tags_parser(self):
        self.assertEqual(rw.frontmatter_tags("---\ntags: [a, 'B']\n---\n"), {"a", "b"})
        self.assertEqual(rw.frontmatter_tags("---\ntitle: x\ntags:\n  - a\n  - b\nnext: y\n---\n"), {"a", "b"})
        self.assertEqual(rw.frontmatter_tags("---\ntags:\n---\n"), set())
        self.assertEqual(rw.frontmatter_tags("no frontmatter"), set())

    def test_missing_list_and_garbage_payload_fail_open(self):
        env = dict(self.env, REJECT_WORDS_FILE=str(self.root / "missing.toml"))
        self.assertIsNone(self.run_hook({"file_path": self.doc(), "content": "frobnicate"}, env=env))
        out = subprocess.run(["python3", str(HOOK)], input="not json",
                             capture_output=True, text=True, env=self.env, timeout=10)
        self.assertEqual((out.returncode, out.stdout), (0, ""))

    def test_state_writes_never_follow_a_symlink(self):
        target = self.root / "target.json"
        target.write_text('{"keep": true}\n')
        sdir = self.root / "state" / "reject-words"
        sdir.mkdir(parents=True)
        (sdir / "s1").symlink_to(target)
        ti = {"file_path": self.doc(), "content": "frobnicate"}
        self.assertIsNone(self.run_hook(ti))
        (sdir / "s1").unlink()
        (sdir / "s1").mkdir()
        digest = __import__("hashlib").sha256(f"{self.doc()}\0frobnicate".encode()).hexdigest()
        (sdir / "s1" / digest).symlink_to(target)
        self.run_hook(ti)
        self.run_hook(ti)
        self.assertEqual(target.read_text(), '{"keep": true}\n')

    def test_unwritable_state_dir_allows(self):
        blocker = self.root / "not-a-dir"
        blocker.write_text("")
        env = dict(self.env, XDG_STATE_HOME=str(blocker))
        self.assertIsNone(self.run_hook({"file_path": self.doc(), "content": "frobnicate"}, env=env))

    def test_malformed_but_valid_json_fails_open(self):
        for payload in ({"tool_input": "x"}, {"tool_input": {"file_path": self.doc(), "edits": ["x"]}},
                        {"session_id": 5, "tool_input": {"file_path": self.doc(), "content": 7}}):
            out = subprocess.run(["python3", str(HOOK)], input=json.dumps(payload),
                                 capture_output=True, text=True, env=self.env, timeout=10)
            self.assertEqual((out.returncode, out.stdout, out.stderr), (0, "", ""), payload)

    def test_shipped_list_rejects_figurative_load_with_the_question(self):
        env = {k: v for k, v in self.env.items() if k != "REJECT_WORDS_FILE"}
        res = self.run_hook({"file_path": self.doc(), "content": "Rows carry keys."}, env=env)
        msg = res["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("[figurative-load]", msg)
        self.assertIn("literal physical object", msg)


if __name__ == "__main__":
    unittest.main()
