#!/usr/bin/env python3
"""End-to-end tests for the station git hook dispatcher (hooks/git/) and its installer.
Run: python3 tests/station-hooks/test-git-dispatch.py

Every repo here sets core.hooksPath in its own config and runs with git's global and
system config switched off, so the station's real settings are never read or changed.
Detector-shaped values are joined at runtime, so this file's source holds none of them.
"""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2] / "hooks" / "git"
SECRET = "sk_live_" + "Ab3dEf6hIj9kLm2nOp5q"
EMAIL = "someone" + "@" + "real-domain.io"


class Station:
    def __init__(self, base: Path, hooks: Path = HOOKS):
        self.base = base
        self.gitconfig = base / "gitconfig"
        self.gitconfig.write_text("")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update({
            "GIT_CONFIG_GLOBAL": str(self.gitconfig), "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(base),
            "GIT_AUTHOR_NAME": "t", "GIT_COMMITTER_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t" + "@" + "example.com", "GIT_COMMITTER_EMAIL": "t" + "@" + "example.com",
            "IDENTIFIER_TERMS_FILE": str(base / "no-list"),
        })
        self.repo = base / "repo"
        self.run("git", "init", "-q", "-b", "main", str(self.repo), cwd=base)
        self.git("config", "core.hooksPath", str(hooks))
        self.write("README.md", "start\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "start")

    def run(self, *args, cwd=None, check=True, input=None):
        return subprocess.run(list(args), cwd=cwd or self.repo, env=self.env, input=input,
                              capture_output=True, text=True, check=check)

    def git(self, *args, check=True, cwd=None):
        return self.run("git", *args, check=check, cwd=cwd)

    def write(self, rel, text, root=None):
        p = (root or self.repo) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def repo_hook(self, name, body):
        p = self.repo / ".git" / "hooks" / name
        p.write_text("#!/bin/sh\n" + body)
        p.chmod(p.stat().st_mode | stat.S_IXUSR)

    def commit(self, msg="change", *extra, cwd=None):
        self.git("add", "-A", cwd=cwd)
        return self.git("commit", "-m", msg, *extra, check=False, cwd=cwd)


class DispatchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Station(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()


class TestCommit(DispatchCase):
    def test_clean_commit_is_silent(self):
        self.st.write("a.md", "hello\n")
        r = self.st.commit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("sanitize gate", r.stderr)

    def test_secret_blocks_the_commit(self):
        self.st.write("a.md", f"key {SECRET}\n")
        r = self.st.commit()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("a.md:1  secret  block", r.stderr)
        self.assertNotIn(SECRET, r.stderr)

    def test_warn_class_commits_with_a_warning(self):
        self.st.write("a.md", f"contact {EMAIL}\n")
        r = self.st.commit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("email  warn", r.stderr)

    def test_pathspec_commit_reads_the_temporary_index(self):
        self.st.write("a.md", "clean\n")
        self.assertEqual(self.st.commit("track a").returncode, 0)
        self.st.write("a.md", f"key {SECRET}\n")              # changed, not staged
        self.st.write("b.md", "clean\n")
        self.st.git("add", "b.md")
        r = self.st.git("commit", "-m", "only a", "--", "a.md", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("a.md:1  secret  block", r.stderr)

    def test_disclosure_message_blocks_and_the_repo_hook_gets_the_message_path(self):
        marker = self.st.base / "msg-arg"
        self.st.repo_hook("commit-msg", f'printf "%s" "$1" > "{marker}"\n')
        self.st.write("a.md", "x\n")
        r = self.st.commit("anonymize the fixtures")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("message:1  disclosure  block", r.stderr)
        self.assertTrue(marker.read_text().endswith("COMMIT_EDITMSG"))

    def test_repo_pre_commit_runs_first_and_its_changes_are_scanned(self):
        self.st.repo_hook("pre-commit", f'printf "key {SECRET}\\n" > added.md && git add added.md\n')
        self.st.write("a.md", "x\n")
        r = self.st.commit()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("added.md:1  secret  block", r.stderr)

    def test_a_failing_repo_hook_stops_the_commit(self):
        self.st.repo_hook("pre-commit", "echo repo-hook-said-no >&2; exit 7\n")
        self.st.write("a.md", "x\n")
        r = self.st.commit()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("repo-hook-said-no", r.stderr)

    def test_other_events_reach_the_repo_hook(self):
        marker = self.st.base / "checked-out"
        self.st.repo_hook("post-checkout", f'touch "{marker}"\n')
        self.st.git("checkout", "-q", "-b", "other")
        self.assertTrue(marker.exists())

    def test_linked_worktree_uses_the_common_hooks(self):
        marker = self.st.base / "committed"
        self.st.repo_hook("post-commit", f'touch "{marker}"\n')
        wt = self.st.base / "wt"
        self.st.git("worktree", "add", "-q", str(wt), "-b", "wt")
        self.st.write("w.md", "clean\n", root=wt)
        r = self.st.commit("from the worktree", cwd=wt)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(marker.exists())
        self.st.write("w.md", f"key {SECRET}\n", root=wt)
        r = self.st.commit("secret in the worktree", cwd=wt)
        self.assertNotEqual(r.returncode, 0)

    def test_a_link_to_dispatch_from_inside_a_repo_does_nothing(self):
        # a repo hook that points back at the dispatcher must not resolve the gate
        # path inside the repo; the station dispatcher still gated the commit first
        (self.st.repo / ".git" / "hooks" / "pre-commit").symlink_to(HOOKS / "dispatch")
        self.st.write("a.md", "clean\n")
        r = self.st.commit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("linked from outside its folder", r.stderr)
        self.st.write("a.md", f"key {SECRET}\n")
        self.assertNotEqual(self.st.commit().returncode, 0)

    def test_missing_gate_lets_the_commit_through_and_says_so(self):
        moved = self.st.base / "hooks-copy"
        moved.mkdir()
        shutil.copy2(HOOKS / "dispatch", moved / "dispatch")
        for name in ("pre-commit", "commit-msg", "pre-push"):
            (moved / name).symlink_to("dispatch")
        self.st.git("config", "core.hooksPath", str(moved))
        self.st.write("a.md", f"key {SECRET}\n")
        r = self.st.commit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("content check did not run", r.stderr)


MDKG = HOOKS.parents[1] / "skills" / "markdown-kg" / "scripts" / "markdown_kg.py"


class TestDocsLinkCheck(DispatchCase):
    """A repo with a docs/ graph: a staged docs note that points at an
    untracked file blocks the commit."""

    def setUp(self):
        super().setUp()
        self.st.write(".gitignore", "kb/\n.kg/\n")
        self.st.write("kb/notes.md", "# Notes\n")
        self.st.write("docs/guide.md", "# Guide\n")
        self.st.git("add", ".gitignore", "docs")
        self.st.git("commit", "-q", "-m", "docs")
        self.st.run("python3", str(MDKG), "ingest", str(self.st.repo / "docs"))

    def stage_and_commit(self, body):
        self.st.write("docs/cite.md", "# Cite\n\n" + body + "\n")
        self.st.git("add", "docs")
        return self.st.git("commit", "-m", "cite", check=False)

    def test_a_link_to_an_untracked_file_blocks_the_commit(self):
        r = self.stage_and_commit("See [notes](../kb/notes.md).")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FORBIDDEN", r.stderr)
        self.assertIn("commit blocked", r.stderr)

    def test_a_code_span_naming_an_untracked_file_blocks_the_commit(self):
        r = self.stage_and_commit("Steps are in `kb/notes.md`.")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("commit blocked", r.stderr)

    def test_a_link_to_a_committed_file_passes(self):
        r = self.stage_and_commit("See [guide](guide.md) and the lane `kb/`.")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_without_a_docs_graph_nothing_runs(self):
        shutil.rmtree(self.st.repo / "docs" / ".kg")
        r = self.stage_and_commit("See [notes](../kb/notes.md).")
        self.assertEqual(r.returncode, 0, r.stderr)


class TestPush(DispatchCase):
    def setUp(self):
        super().setUp()
        self.remote = self.st.base / "remote.git"
        self.st.run("git", "init", "-q", "--bare", str(self.remote), cwd=self.st.base)
        self.st.git("remote", "add", "origin", str(self.remote))
        self.st.git("push", "-q", "origin", "main")

    def test_content_committed_with_no_verify_is_stopped_at_push(self):
        self.st.write("a.md", f"key {SECRET}\n")
        r = self.st.commit("x", "--no-verify")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.st.git("push", "origin", "main", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("secret  block", r.stderr)
        r = self.st.git("push", "--no-verify", "origin", "main", check=False)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_update_instead_still_updates_the_work_tree(self):
        # push-to-checkout is deliberately unlinked: its mere presence would hand the
        # work-tree update to a hook that does nothing
        work = self.st.base / "work"
        self.st.run("git", "clone", "-q", "-b", "main", str(self.remote), str(work), cwd=self.st.base)
        self.st.git("config", "receive.denyCurrentBranch", "updateInstead", cwd=work)
        self.st.git("remote", "add", "work", str(work))
        self.st.write("a.md", "pushed content\n")
        self.assertEqual(self.st.commit().returncode, 0)
        r = self.st.git("push", "work", "main", check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((work / "a.md").read_text(), "pushed content\n")

    def test_a_refspec_push_is_scanned_and_the_repo_hook_gets_the_list(self):
        marker = self.st.base / "pushed"
        self.st.repo_hook("pre-push", f'cat > "{marker}"\n')
        self.st.write("a.md", "clean\n")
        self.assertEqual(self.st.commit().returncode, 0)
        r = self.st.git("push", "origin", "main:release", check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("refs/heads/release", marker.read_text())


class TestInstaller(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.cfg = base / "gitconfig"
        self.cfg.write_text("")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update({"GIT_CONFIG_GLOBAL": str(self.cfg), "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(base)})

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, *args):
        return subprocess.run(["sh", str(HOOKS / "install.sh"), *args], env=self.env,
                              capture_output=True, text=True)

    def value(self):
        return subprocess.run(["git", "config", "--global", "--get", "core.hooksPath"], env=self.env,
                              capture_output=True, text=True).stdout.strip()

    def test_install_check_and_uninstall(self):
        self.assertEqual(self.install("--check").returncode, 1)
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.value(), str(HOOKS.resolve()))
        self.assertEqual(self.install("--check").returncode, 0)
        self.assertEqual(self.install().returncode, 0)          # already installed
        self.assertEqual(self.install("--uninstall").returncode, 0)
        self.assertEqual(self.value(), "")

    def test_an_existing_value_is_not_replaced_without_force(self):
        subprocess.run(["git", "config", "--global", "core.hooksPath", "/somewhere/else"], env=self.env, check=True)
        r = self.install()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.value(), "/somewhere/else")
        self.assertEqual(self.install("--uninstall").returncode, 0)
        self.assertEqual(self.value(), "/somewhere/else")       # not ours, left alone
        self.assertEqual(self.install("--force").returncode, 0)
        self.assertEqual(self.value(), str(HOOKS.resolve()))


if __name__ == "__main__":
    unittest.main()
