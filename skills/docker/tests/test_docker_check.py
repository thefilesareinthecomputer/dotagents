#!/usr/bin/env python3
"""Tests for docker_check.py - stdlib only.

    python3 -m unittest discover skills/docker/tests

The quiet test matters most. A container linter that fires on a correct
Dockerfile gets muted within a day, and a muted linter protects nothing.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "docker_check.py"
BAD = ROOT / "tests" / "fixtures" / "bad"
GOOD = ROOT / "tests" / "fixtures" / "good"


def run(*paths: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *[str(p) for p in paths]],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout


class TestComposeFilenames(unittest.TestCase):
    """A compose file the classifier does not recognize is scanned by nothing and
    still reports clean, which reads as a pass. The scaffold prescribes
    compose.dev.yml / compose.prod.yml, so those must classify."""

    def _classify(self, name: str) -> str | None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import docker_check

        return docker_check.classify(Path(name))

    def test_recognizes_env_suffixed_variants(self) -> None:
        for name in (
            "compose.yml", "compose.yaml",
            "docker-compose.yml", "docker-compose.yaml",
            "compose.dev.yml", "compose.prod.yml", "compose.prod.yaml",
            "docker-compose.override.yml", "compose.dev.local.yml",
        ):
            with self.subTest(name=name):
                self.assertEqual(self._classify(name), "compose")

    def test_ignores_lookalikes(self) -> None:
        for name in ("composer.yml", "mycompose.yml", "values.yml", "compose.txt"):
            with self.subTest(name=name):
                self.assertIsNone(self._classify(name))

    def test_suffixed_compose_is_actually_scanned(self) -> None:
        """End to end: a hazard in compose.prod.yml must fail the gate."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "compose.prod.yml"
            path.write_text("services:\n  app:\n    privileged: true\n")
            code, out = run(path)
            self.assertEqual(code, 1, "hazard in compose.prod.yml must block")
            self.assertIn("privileged", out)


class TestCatchesHazards(unittest.TestCase):
    def setUp(self) -> None:
        self.code, self.out = run(BAD)

    def test_blocks(self) -> None:
        self.assertEqual(self.code, 1, "hazardous fixtures must fail the gate")

    def test_catches_host_escapes(self) -> None:
        """The grants that make a container escape into a host compromise."""
        for rule in (
            "docker-socket-mount", "privileged", "root-fs-mount", "sensitive-mount",
            "namespace-host", "cap-dangerous", "unconfined-profile",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, self.out)

    def test_socket_at_run_path(self) -> None:
        """/run/docker.sock - the modern path - must FAIL, not just /var/run."""
        self.assertIn("/run/docker.sock:/run/docker.sock", (BAD / "docker-compose.yml").read_text())
        self.assertIn("docker-socket-mount", self.out)

    def test_commented_grant_does_not_fire(self) -> None:
        """A commented `# privileged: true` is inert; firing on it mutes the tool."""
        self.assertEqual(self.out.count("privileged: true disables"), 1)

    def test_catches_baked_secrets(self) -> None:
        for rule in ("secret-in-layer", "secret-literal", "secret-in-compose"):
            with self.subTest(rule=rule):
                self.assertIn(rule, self.out)

    def test_catches_supply_chain(self) -> None:
        for rule in ("add-remote-url", "curl-pipe-sh", "latest-tag"):
            with self.subTest(rule=rule):
                self.assertIn(rule, self.out)

    def test_catches_hygiene(self) -> None:
        for rule in ("runs-as-root", "no-healthcheck", "no-dockerignore", "cache-busting-copy"):
            with self.subTest(rule=rule):
                self.assertIn(rule, self.out)


class TestStaysQuiet(unittest.TestCase):
    def test_good_fixtures_are_silent(self) -> None:
        code, out = run(GOOD)
        self.assertEqual(code, 0, f"correct Dockerfile must pass; got:\n{out}")
        for severity in ("FAIL:", "WARN:"):
            self.assertNotIn(severity, out, f"false positive on good fixtures:\n{out}")


class TestHostileInput(unittest.TestCase):
    """It reads files it did not write. Untrusted input must not hang it.

    These payloads are built from MANY sub-2000-char lines - an earlier version
    of this test used two 60k-char lines, which the length cap skipped entirely,
    so it would have passed against a pattern that hangs for an hour. It also now
    exercises check_COMPOSE, where the actual ReDoS defect lived (secret-in-compose).
    """

    def _time(self, fn, content: str) -> float:
        import time

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ("Dockerfile" if fn == "d" else "docker-compose.yml")
            path.write_text(content)
            sys.path.insert(0, str(ROOT / "scripts"))
            import docker_check

            check = docker_check.check_dockerfile if fn == "d" else docker_check.check_compose
            start = time.perf_counter()
            check(path)
            return time.perf_counter() - start

    def test_compose_secret_no_redos(self) -> None:
        # Many legal-length lines resembling the ambiguous secret pattern.
        payload = "\n".join("      PASSWORD" + "a" * 1900 for _ in range(500))
        self.assertLess(self._time("c", payload), 1.0, "secret-in-compose ReDoS")

    def test_dockerfile_many_lines_no_redos(self) -> None:
        payload = "\n".join("RUN apt-get install " + "a" * 1900 for _ in range(500))
        self.assertLess(self._time("d", payload), 1.0, "dockerfile ReDoS")

    def test_overlong_line_fails_closed(self) -> None:
        """A line too long to scan must be reported, not silently dropped -
        else a padded ENV API_KEY=... slips the gate."""
        code, out = run_str("ENV API_KEY=sk-live-secret " + "x" * 2100)
        self.assertIn("line-too-long", out)


def run_str(dockerfile_body: str) -> tuple[int, str]:
    import os

    d = tempfile.mkdtemp()
    p = Path(d) / "Dockerfile"
    p.write_text(dockerfile_body + "\n")
    try:
        return run(p)
    finally:
        p.unlink()
        os.rmdir(d)


class TestSkillStructure(unittest.TestCase):
    def test_skill_md_bounded(self) -> None:
        body = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertLess(len(body.splitlines()), 500)

    def test_name_matches_directory(self) -> None:
        head = (ROOT / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        self.assertIn(f"name: {ROOT.name}", head)

    def test_no_version_footer(self) -> None:
        for md in ROOT.rglob("*.md"):
            self.assertNotRegex(md.read_text(encoding="utf-8"), r"(?m)^Version:")

    def test_evals_have_negative_case(self) -> None:
        cases = json.loads((ROOT / "evals" / "triggers.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 3)
        self.assertTrue(any(not c["should_trigger"] for c in cases))


if __name__ == "__main__":
    unittest.main()
