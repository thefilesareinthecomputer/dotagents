#!/usr/bin/env python3
"""Tests for `sanitize.py gate` against throwaway repos.

Each repo runs with git's global and system config switched off, so a station's own
hooks path or settings never reach it, and with an invented term list. Every
detector-shaped value is joined at runtime, so this file's source holds none of them.
Run: python3 -m unittest discover -s skills/sanitize/tests -v
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SANITIZE = SCRIPTS / "sanitize.py"
sys.path.insert(0, str(SCRIPTS))

SECRET = "sk_live_" + "Ab3dEf6hIj9kLm2nOp5q"
EMAIL = "someone" + "@" + "real-domain.io"
TERM = "zorbulate"


class Repo:
    def __init__(self, root: Path, terms: Path | None):
        self.root = root
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        empty = root.parent / "empty-gitconfig"
        empty.write_text("")
        self.env.update({
            "GIT_CONFIG_GLOBAL": str(empty), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t", "GIT_COMMITTER_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t" + "@" + "example.com", "GIT_COMMITTER_EMAIL": "t" + "@" + "example.com",
            "IDENTIFIER_TERMS_FILE": str(terms) if terms else str(root.parent / "no-such-list"),
        })
        root.mkdir()
        self.git("init", "-q", "-b", "main")

    def git(self, *args, input=None):
        return subprocess.run(["git", *args], cwd=self.root, env=self.env, input=input,
                              capture_output=True, text=True, check=True).stdout

    def write(self, rel, text, mode="w"):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            p.write_bytes(text)
        else:
            with open(p, mode, encoding="utf-8") as fh:
                fh.write(text)

    def commit(self, msg="change"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD").strip()

    def gate(self, *args, stdin=None):
        p = subprocess.run([sys.executable, str(SANITIZE), "gate", *args], cwd=self.root, env=self.env,
                           input=stdin, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr


class GateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.terms = base / "terms.txt"
        self.terms.write_text(TERM + "\n")
        self.repo = Repo(base / "repo", self.terms)

    def tearDown(self):
        self.tmp.cleanup()


class TestStaged(GateCase):
    def test_clean_commit_is_silent(self):
        self.repo.write("a.md", "hello\n")
        self.repo.git("add", "-A")
        self.assertEqual(self.repo.gate("--staged"), (0, ""))

    def test_secret_blocks_without_printing_the_value(self):
        self.repo.write("cfg.md", f"line one\nkey {SECRET}\n")
        self.repo.git("add", "-A")
        code, out = self.repo.gate("--staged")
        self.assertEqual(code, 3, out)
        self.assertIn("cfg.md:2  secret  block", out)
        self.assertNotIn(SECRET, out)

    def test_warn_class_passes_with_a_warning(self):
        self.repo.write("a.md", f"contact {EMAIL}\nabout {TERM}\n")
        self.repo.git("add", "-A")
        code, out = self.repo.gate("--staged")
        self.assertEqual(code, 0, out)
        self.assertIn("a.md:1  email  warn", out)
        self.assertIn("a.md:2  term  warn", out)
        self.assertNotIn(EMAIL, out)
        self.assertNotIn(TERM + " ", out.replace("term  warn", ""))

    def test_only_added_lines_count(self):
        self.repo.write("a.md", f"contact {EMAIL}\n")
        self.repo.commit()
        self.repo.write("a.md", "clean addition\n", mode="a")
        self.repo.git("add", "-A")
        self.assertEqual(self.repo.gate("--staged"), (0, ""))

    def test_a_key_block_split_across_hunks_is_still_one_secret(self):
        begin = "-----" + "BEGIN " + "PRIVATE KEY" + "-----"
        end = "-----" + "END " + "PRIVATE KEY" + "-----"
        self.repo.write("k.txt", f"{begin}\n{end}\n")
        self.repo.commit()
        self.repo.write("k.txt", f"{begin}\n{'Q' * 64}\n{end}\n")
        self.repo.git("add", "-A")
        code, out = self.repo.gate("--staged")
        self.assertEqual(code, 3, out)

    def test_hidden_character_attack_blocks(self):
        self.repo.write("a.md", "run " + chr(0x202E) + "this\n")
        self.repo.git("add", "-A")
        code, out = self.repo.gate("--staged")
        self.assertEqual(code, 3, out)
        self.assertIn("invisible(bidi-override)  block", out)

    def test_lockfiles_and_binaries_are_skipped(self):
        self.repo.write("uv.lock", f"key {SECRET}\n")
        self.repo.write("blob.bin", b"\0\0" + SECRET.encode())
        self.repo.git("add", "-A")
        self.assertEqual(self.repo.gate("--staged"), (0, ""))

    def test_a_renamed_file_does_not_re_report_old_lines(self):
        self.repo.write("old.md", f"contact {EMAIL}\n" + "".join(f"line {i}\n" for i in range(20)))
        self.repo.commit()
        self.repo.git("mv", "old.md", "new.md")
        self.assertEqual(self.repo.gate("--staged"), (0, ""))

    def test_an_odd_path_is_printed_escaped(self):
        self.repo.write("we\tird.md", f"key {SECRET}\n")
        self.repo.git("add", "-A")
        code, out = self.repo.gate("--staged")
        self.assertEqual(code, 3, out)
        self.assertIn("we\\tird.md:1", out)

    def test_a_path_with_a_space_is_scanned_not_refused(self):
        self.repo.write("a b.txt", "clean\n")
        self.repo.git("add", "-A")
        self.assertEqual(self.repo.gate("--staged"), (0, ""))
        self.repo.write("c d.txt", f"key {SECRET}\n")
        self.repo.git("add", "-A")
        code, out = self.repo.gate("--staged")
        self.assertEqual(code, 3, out)
        self.assertIn("c d.txt:1  secret  block", out)
        self.assertNotIn("cannot read", out)

    def test_a_submodule_pointer_passes(self):
        self.repo.git("update-index", "--add", "--cacheinfo", "160000," + "a1b2c3d4" * 5 + ",sub")
        self.assertEqual(self.repo.gate("--staged"), (0, ""))

    def test_a_lone_cr_or_a_plus_plus_line_cannot_hide_later_hunks(self):
        filler = "".join(f"line {n}\n" for n in range(40))
        for n, lead in enumerate(("x\r+++ /dev/null\n", "++ /dev/null\n")):
            name = f"f{n}.txt"
            self.repo.write(name, "start\n")
            self.repo.git("add", "-A")
            self.repo.git("commit", "-q", "-m", f"base {n}")
            self.repo.write(name, "start\n" + lead + filler + f"key {SECRET}\n")
            self.repo.git("add", "-A")
            code, out = self.repo.gate("--staged")
            self.assertEqual(code, 3, (lead, out))
            self.repo.git("reset", "-q", "--hard")

    def test_a_diff_attribute_cannot_hide_a_file(self):
        self.repo.write(".gitattributes", "notes.txt -diff\n")
        self.repo.write("notes.txt", f"key {SECRET}\n")
        self.repo.git("add", "-A")
        code, out = self.repo.gate("--staged")
        self.assertEqual(code, 3, out)

    def test_a_nul_byte_in_a_text_file_warns(self):
        self.repo.write("notes.md", b"\0" + f"key {SECRET}\n".encode())
        self.repo.write("pic.png", b"\x89PNG\0\0" + SECRET.encode())
        self.repo.git("add", "-A")
        code, out = self.repo.gate("--staged")
        self.assertEqual(code, 0, out)
        self.assertIn("notes.md:0  binary-skipped  warn", out)
        self.assertNotIn("pic.png", out)

    def test_missing_term_list_is_said_once_and_secrets_still_block(self):
        self.repo.env["IDENTIFIER_TERMS_FILE"] = str(Path(self.tmp.name) / "absent.txt")
        self.repo.write("a.md", f"{TERM}\nkey {SECRET}\n")
        self.repo.git("add", "-A")
        code, out = self.repo.gate("--staged")
        self.assertEqual(code, 3, out)
        self.assertEqual(out.count("term check was skipped"), 1)
        self.assertNotIn("term  warn", out)

    def test_a_typical_commit_is_fast(self):
        for i in range(6):
            self.repo.write(f"f{i}.md", "".join(f"prose line {n} about things\n" for n in range(200)))
        self.repo.git("add", "-A")
        start = time.monotonic()
        self.assertEqual(self.repo.gate("--staged")[0], 0)
        self.assertLess(time.monotonic() - start, 1.5)


class TestRangesAndRefs(GateCase):
    def setUp(self):
        super().setUp()
        self.repo.write("a.md", "start\n")
        self.base = self.repo.commit("start")

    def test_secret_added_then_removed_still_blocks(self):
        self.repo.write("a.md", f"key {SECRET}\n", mode="a")
        self.repo.commit()
        self.repo.write("a.md", "start\n")
        self.repo.commit()
        code, out = self.repo.gate("--range", f"{self.base}..HEAD")
        self.assertEqual(code, 3, out)
        self.assertIn(":a.md:2  secret  block", out)

    def test_a_message_in_the_range_is_checked(self):
        self.repo.write("b.md", "x\n")
        self.repo.commit("anonymize the fixtures")
        code, out = self.repo.gate("--range", f"{self.base}..HEAD")
        self.assertEqual(code, 3, out)
        self.assertIn(":message:1  disclosure  block", out)

    def test_conflict_resolution_content_is_caught(self):
        self.repo.git("checkout", "-q", "-b", "side")
        self.repo.write("a.md", "side change\n")
        self.repo.commit("side")
        self.repo.git("checkout", "-q", "main")
        self.repo.write("a.md", "main change\n")
        self.repo.commit("main")
        subprocess.run(["git", "merge", "-q", "side"], cwd=self.repo.root, env=self.repo.env,
                       capture_output=True)
        self.repo.write("a.md", f"resolved with key {SECRET}\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "merge side")
        code, out = self.repo.gate("--range", "HEAD^1..HEAD")
        self.assertEqual(code, 3, out)

    def test_pre_push_tuples(self):
        self.repo.write("a.md", f"key {SECRET}\n", mode="a")
        head = self.repo.commit()
        zero = "0" * 40
        new_ref = f"refs/heads/main {head} refs/heads/main {zero}\n"
        self.assertEqual(self.repo.gate("--refs", "--remote", "origin", stdin=new_ref)[0], 3)
        known = f"refs/heads/main {head} refs/heads/main {self.base}\n"
        self.assertEqual(self.repo.gate("--refs", "--remote", "origin", stdin=known)[0], 3)
        unfetched = f"refs/heads/main {head} refs/heads/main {'1' * 40}\n"
        self.assertEqual(self.repo.gate("--refs", "--remote", "origin", stdin=unfetched)[0], 3)
        deleted = f"(delete) {zero} refs/heads/old {head}\n"
        self.assertEqual(self.repo.gate("--refs", "--remote", "origin", stdin=deleted), (0, ""))

    def test_an_unreadable_range_blocks(self):
        code, out = self.repo.gate("--range", "nosuchref..HEAD")
        self.assertEqual(code, 3, out)
        self.assertIn("not a clean result", out)


class TestMessageAndFiles(GateCase):
    def test_message_rules(self):
        msg = Path(self.tmp.name) / "MSG"
        msg.write_text("fix the parser\n# anonymize is in a comment and git drops it\n")
        self.assertEqual(self.repo.gate("--message", str(msg)), (0, ""))
        msg.write_text("anonymize the fixtures\n")
        self.assertEqual(self.repo.gate("--message", str(msg))[0], 3)
        msg.write_text(f"touch {TERM} notes\n")
        code, out = self.repo.gate("--message", str(msg))
        self.assertEqual(code, 0, out)
        self.assertIn("message:1  term  warn", out)

    def test_files_use_the_review_tier_and_its_path_rule(self):
        self.repo.write("skills/x/SKILL.md", f"about {TERM}\n")
        self.repo.write("tasks/plan.md", f"about {TERM}\n")
        code, out = self.repo.gate("--files", "skills/x/SKILL.md", "tasks/plan.md")
        self.assertEqual(code, 3, out)
        self.assertIn("skills/x/SKILL.md:1  term  block", out)
        self.assertIn("tasks/plan.md:1  term  warn", out)


class TestPatchParsing(unittest.TestCase):
    """added_lines reads git's patch text; these pin the header rules directly."""

    def test_a_hash_containing_the_gitlink_mode_is_still_a_file(self):
        import gate
        patch = (b"diff --git a/x.txt b/x.txt\nnew file mode 100644\nindex 0000000..f160000\n"
                 b"--- /dev/null\n+++ b/x.txt\n@@ -0,0 +1 @@\n+content\n")
        self.assertEqual(gate.added_lines(patch), {"x.txt": {1}})

    def test_a_real_gitlink_is_skipped(self):
        import gate
        new = (b"diff --git a/sub b/sub\nnew file mode 160000\nindex 0000000..a1b2c3d\n"
               b"--- /dev/null\n+++ b/sub\n@@ -0,0 +1 @@\n+Subproject commit " + b"a1" * 20 + b"\n")
        bump = (b"diff --git a/sub b/sub\nindex a1b2c3d..d4e5f6a 160000\n"
                b"--- a/sub\n+++ b/sub\n@@ -1 +1 @@\n-Subproject commit x\n+Subproject commit y\n")
        self.assertEqual(gate.added_lines(new), {})
        self.assertEqual(gate.added_lines(bump), {})


class TestInbox(GateCase):
    def test_an_inbox_file_blocks_by_path(self):
        for root in (".claude", ".agents"):
            self.repo.write(f"{root}/inbox/20260101000000-001__hello.md", "a plain message\n")
        self.repo.git("add", "-A")
        code, out = self.repo.gate("--staged")
        self.assertEqual(code, 3, out)
        self.assertIn(".claude/inbox/20260101000000-001__hello.md:0  inbox  block", out)
        self.assertIn(".agents/inbox/20260101000000-001__hello.md:0  inbox  block", out)
        self.assertIn("AGENT_MAIL_COMMIT_INBOX=1", out)

    def test_the_bypass_lifts_the_inbox_rule_and_nothing_else(self):
        self.repo.write(".claude/inbox/m.md", "a plain message\n")
        self.repo.git("add", "-A")
        self.repo.env["AGENT_MAIL_COMMIT_INBOX"] = "1"
        self.assertEqual(self.repo.gate("--staged"), (0, ""))
        self.repo.write(".claude/inbox/m.md", f"key {SECRET}\n", mode="a")
        self.repo.git("add", "-A")
        code, out = self.repo.gate("--staged")
        self.assertEqual(code, 3, out)
        self.assertNotIn("inbox  block", out)

    def test_removing_an_inbox_file_and_other_inbox_names_pass(self):
        self.repo.write(".claude/inbox/old.md", "x\n")
        self.repo.env["AGENT_MAIL_COMMIT_INBOX"] = "1"
        self.repo.commit()
        del self.repo.env["AGENT_MAIL_COMMIT_INBOX"]
        self.repo.git("rm", "-q", "--cached", ".claude/inbox/old.md")
        self.repo.write("docs/inbox/notes.md", "x\n")
        self.repo.write("claude/inbox/notes.md", "x\n")
        self.repo.git("add", "docs", "claude")
        self.assertEqual(self.repo.gate("--staged"), (0, ""))


class TestLargeFiles(GateCase):
    def test_a_large_text_file_is_scanned_around_the_change(self):
        filler = "".join(f"journal line {i} with ordinary words\n" for i in range(300_000))
        self.assertGreater(len(filler), 8 * 1024 * 1024)
        self.repo.write("journal.md", filler)
        self.repo.commit()
        self.repo.write("journal.md", f"today's entry, key {SECRET}\n", mode="a")
        self.repo.git("add", "-A")
        start = time.monotonic()
        code, out = self.repo.gate("--staged")
        self.assertEqual(code, 3, out)
        self.assertIn("journal.md:300001  secret  block", out)
        self.assertLess(time.monotonic() - start, 5)

    def test_windowed_text_keeps_line_numbers_and_blanks_far_lines(self):
        import gate
        data = b"".join(b"line %d\n" % i for i in range(1, 1001))
        text = gate.windowed(data, {500})
        lines = text.split("\n")
        self.assertEqual(lines[499], "line 500")
        self.assertEqual(lines[499 - gate.WINDOW_LINES], "line %d" % (500 - gate.WINDOW_LINES))
        self.assertEqual(lines[499 - gate.WINDOW_LINES - 1], "")
        self.assertEqual(lines[0], "")

    def test_a_text_file_over_the_cap_blocks_instead_of_passing(self):
        import gate

        class Blobs:
            def read(self, rev, path):
                return b"ordinary text\n" * 20

        with mock.patch.object(gate, "MAX_TEXT_BYTES", 100):
            found = gate.scan_blob(Blobs(), "", "big.md", {1}, set(), "")
        self.assertEqual([(f.cls, f.tier) for f in found], [("too-large", "block")])

    def test_a_binary_over_the_cap_is_still_skipped(self):
        import gate

        class Blobs:
            def read(self, rev, path):
                return b"\0" * 200

        with mock.patch.object(gate, "MAX_TEXT_BYTES", 100):
            self.assertEqual(gate.scan_blob(Blobs(), "", "movie.mp4", {1}, set(), ""), [])


class TestFailureMode(unittest.TestCase):
    def test_a_bug_in_the_gate_lets_the_commit_through(self):
        import gate
        with mock.patch.object(gate, "staged", side_effect=RuntimeError("boom")), \
             mock.patch.object(gate, "repo_root", return_value=None):
            self.assertEqual(gate.main(["--staged"]), 0)


if __name__ == "__main__":
    unittest.main()
