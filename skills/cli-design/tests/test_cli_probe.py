"""Tests for scripts/cli_probe.py. Run with:

    python3 -m unittest discover -s tests
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
PROBE = os.path.join(SCRIPTS, "cli_probe.py")
FIXTURES = os.path.join(HERE, "fixtures")

sys.path.insert(0, SCRIPTS)
import cli_probe  # noqa: E402


def fixture(name):
    return [sys.executable, os.path.join(FIXTURES, name)]


def run_probe(*args):
    """Drive the probe through its command line, the way a user does."""
    return subprocess.run([sys.executable, PROBE, *args], stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)


def statuses(proc):
    return {r["check"]: r["status"] for r in json.loads(proc.stdout)["results"]}


class ParsesAsJson(unittest.TestCase):
    def test_one_value(self):
        self.assertTrue(cli_probe.parses_as_json('[{"a": 1}]\n'))

    def test_json_lines(self):
        self.assertTrue(cli_probe.parses_as_json('{"a": 1}\n{"a": 2}\n'))

    def test_empty_is_not_json(self):
        self.assertFalse(cli_probe.parses_as_json("  \n"))

    def test_prose_is_not_json(self):
        self.assertFalse(cli_probe.parses_as_json("rows: 2\n"))

    def test_json_then_prose_is_not_json(self):
        self.assertFalse(cli_probe.parses_as_json('{"a": 1}\ndone\n'))


class Patterns(unittest.TestCase):
    def test_ansi_matches_color_and_cursor_codes(self):
        self.assertTrue(cli_probe.ANSI.search("\x1b[1mbold\x1b[0m"))
        self.assertTrue(cli_probe.ANSI.search("\x1b[?25l"))

    def test_ansi_ignores_plain_brackets(self):
        self.assertFalse(cli_probe.ANSI.search("usage: tool [-h] [--json]"))

    def test_first_line_skips_blank_lines(self):
        self.assertEqual(cli_probe.first_line("\n\n  tool 1.2\nmore"), "tool 1.2")


class GoodProgram(unittest.TestCase):
    def test_passes_every_default_check(self):
        proc = run_probe("--json", "--", *fixture("good_cli.py"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        found = statuses(proc)
        self.assertNotIn("fail", found.values())
        self.assertNotIn("warn", found.values())
        for check in ("help", "help-examples", "help-short", "version",
                      "usage-exit", "usage-stream", "usage-hint"):
            self.assertEqual(found[check], "pass", check)

    def test_optional_checks_pass(self):
        proc = run_probe("--json", "--sub", "list", "--no-args", "--json-args", "list --json",
                         "--", *fixture("good_cli.py"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        found = statuses(proc)
        self.assertEqual(found["sub-help"], "pass")
        self.assertEqual(found["no-args"], "pass")
        self.assertEqual(found["json"], "pass")

    def test_report_is_stable_across_runs(self):
        first = run_probe("--json", "--", *fixture("good_cli.py"))
        second = run_probe("--json", "--", *fixture("good_cli.py"))
        self.assertEqual(first.stdout, second.stdout)

    def test_human_report_is_plain_text(self):
        proc = run_probe("--", *fixture("good_cli.py"))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("0 failed", proc.stdout)
        self.assertNotIn("\x1b", proc.stdout)
        self.assertEqual(proc.stderr, "")


class BadProgram(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc = run_probe("--json", "--json-args", "dump", "--", *fixture("bad_cli.py"))
        cls.found = statuses(cls.proc)

    def test_exits_one(self):
        self.assertEqual(self.proc.returncode, 1)

    def test_names_each_fault(self):
        for check in ("help-exit", "help-stream", "plain-when-piped",
                      "usage-exit", "usage-stream", "usage-trace", "json"):
            self.assertEqual(self.found[check], "fail", check)

    def test_missing_short_help_and_version_are_warnings(self):
        self.assertEqual(self.found["help-short"], "warn")
        self.assertEqual(self.found["version"], "warn")


class StrictMode(unittest.TestCase):
    def test_a_warning_fails_only_with_strict(self):
        # tty_color_cli.py has one failure, so use a program whose only fault is a warning.
        argv = [sys.executable, "-c",
                "import sys\n"
                "a = sys.argv[1:]\n"
                "if '--help' in a or '-h' in a: print('tool: does a thing'); sys.exit(0)\n"
                "if '--version' in a: print('tool 1.0'); sys.exit(0)\n"
                "sys.stderr.write('tool: unknown option; see --help\\n'); sys.exit(2)\n"]
        loose = run_probe("--json", "--", *argv)
        self.assertEqual(loose.returncode, 0, loose.stdout)
        self.assertEqual(statuses(loose)["help-examples"], "warn")
        strict = run_probe("--strict", "--json", "--", *argv)
        self.assertEqual(strict.returncode, 1)


class Lifecycle(unittest.TestCase):
    def test_a_program_that_never_returns_is_reported_and_stopped(self):
        marker = "cli-probe-test-%d" % os.getpid()
        proc = run_probe("--json", "--timeout", "1", "--",
                         *fixture("hang_cli.py"), marker)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        results = json.loads(proc.stdout)["results"]
        self.assertTrue(all(r["status"] in ("fail", "skip") for r in results), results)
        self.assertTrue(any(r["check"] == "no-hang" for r in results))
        listing = subprocess.run(["ps", "-axo", "command"], stdout=subprocess.PIPE,
                                 text=True, timeout=10).stdout
        self.assertNotIn(marker, listing, "a probed child outlived the probe")


@unittest.skipIf(os.name == "nt", "no pseudo-terminal on Windows")
class HangOnTerminal(unittest.TestCase):
    def test_a_program_that_hangs_only_on_a_terminal_is_not_passed(self):
        argv = [sys.executable, "-c",
                "import sys, time\n"
                "a = sys.argv[1:]\n"
                "if '--help' in a or '-h' in a:\n"
                "    if sys.stdout.isatty():\n"
                "        time.sleep(600)\n"
                "    print('tool: example: tool run'); sys.exit(0)\n"
                "if '--version' in a: print('tool 1.0'); sys.exit(0)\n"
                "sys.stderr.write('tool: unknown option; see --help\\n'); sys.exit(2)\n"]
        proc = run_probe("--json", "--timeout", "1", "--", *argv)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        results = json.loads(proc.stdout)["results"]
        by_check = {r["check"]: r["status"] for r in results}
        self.assertEqual(by_check["no-color"], "skip")
        self.assertEqual(by_check["no-hang"], "fail")


@unittest.skipIf(os.name == "nt", "no pseudo-terminal on Windows")
class NoColor(unittest.TestCase):
    def test_color_on_a_terminal_despite_no_color_fails(self):
        proc = run_probe("--json", "--", *fixture("tty_color_cli.py"))
        self.assertEqual(proc.returncode, 1)
        found = statuses(proc)
        self.assertEqual(found["no-color"], "fail")
        self.assertEqual(found["help"], "pass")

    def test_respecting_no_color_passes(self):
        proc = run_probe("--json", "--", *fixture("good_cli.py"))
        self.assertEqual(statuses(proc)["no-color"], "pass")


class ProbeUsage(unittest.TestCase):
    def test_no_command_is_a_usage_error(self):
        proc = run_probe()
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("after `--`", proc.stderr)

    def test_missing_program_is_reported_without_a_trace(self):
        proc = run_probe("--", "cli-probe-no-such-program")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("cannot find", proc.stderr)

    def test_bad_timeout_is_a_usage_error(self):
        proc = run_probe("--timeout", "0", "--", *fixture("good_cli.py"))
        self.assertEqual(proc.returncode, 2)

    def test_the_probe_passes_its_own_checks(self):
        proc = run_probe("--strict", "--json", "--", sys.executable, PROBE)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
