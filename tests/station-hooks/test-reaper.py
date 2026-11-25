#!/usr/bin/env python3
"""Tests for the reaper.py SessionStart hook and its --report mode.
Target: the repo's hooks/reaper.py by default; HOOK_UNDER_TEST points the run at a station
copy such as ~/.claude/hooks/reaper.py.
Run: python3 tests/station-hooks/test-reaper.py   (or via unittest discover)

Contract: from a `ps` listing, report the user's heavy interpreter or agent processes that
are orphaned, or that have run under a session for over an hour, and any process of the
user's that has averaged 25% CPU or more for over an hour (a hog); never a session itself,
another user's process, a light daemon or app, or an ignored one. An orphaned agent browser
(marked by its launch flags) is reported at any CPU with its process group's totals, and so is
an orphaned browser MCP server; the user's own browser never is. Other events print nothing;
--report prints the same findings as plain text. Home paths and long tokens are masked.
It only reports. Fails open.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TARGET = Path(os.environ.get("HOOK_UNDER_TEST") or Path(__file__).resolve().parents[2] / "hooks" / "reaper.py")
UID = os.getuid()
HOME = str(Path.home())
# Stand-in secrets in the detector's all-x placeholder form, written into LISTING below.
SECRETS = ("tok_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "pw_xxxxxxxx", "url_xxxxxxxx",
           "bearer_xxxxxxxxxxxxxxxx")
LAUNCHD = "    1     0     1     0 04-00:00:00   10:00.00   9000 /sbin/launchd\n"

# pid ppid pgid uid etime time rss command
LISTING = LAUNCHD + f"""\
 9665     1  9665 {UID} 01-16:17:46 1724:00.00 2150816 /opt/homebrew/bin/Python -I -
 2627     1  2627 {UID} 03-22:38:43   9:48.91 135472 {HOME}/.bun/bin/bun {HOME}/.claude/plugins/x/worker-service.cjs --daemon
  700     1   700 {UID}    02:00:00   10:00.00  50000 /System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal
22169 22153 22153 {UID}    18:53:56  403:23.00 190000 /Applications/Browser.app/Contents/Frameworks/Helpers/Browser Helper (Renderer).app/Contents/MacOS/Browser Helper (Renderer)
22153     1 22153 {UID}    19:10:36   20:00.00 300000 /Applications/Browser.app/Contents/MacOS/Browser
 7100     1  7100 {UID}    00:40:00   35:00.00  50000 /Applications/Encoder.app/Contents/MacOS/Encoder
 5662     1  5662 {UID} 01-04:17:53  300:00.00 255000 /Users/x/.local/bin/2.1.310
 7000  5662  7000 {UID}    03:00:00    0:01.00   4000 /bin/zsh -c node build.js
 7001  7000  7000 {UID}    03:00:00  120:00.00  80000 node {HOME}/proj/build.js --token tok_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
 7002  5662  5662 {UID}    00:20:00   15:00.00  80000 python3 short-but-busy.py
 8000     1  8000   502    05:00:00  290:00.00  80000 python3 someone-elses.py
 8100     1  8100 {UID}    05:00:00  250:00.00  80000 python3 {HOME}/srv/ignored-daemon.py
 8200     1  8200 {UID}    00:30:00    0:10.00 3000000 python3 big-but-idle.py --password pw_xxxxxxxx https://user:url_xxxxxxxx@example.com/x -H Authorization: Bearer bearer_xxxxxxxxxxxxxxxx
"""

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HELPER = ("/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Framework.framework/Helpers/"
          "Google Chrome Helper (Renderer).app/Contents/MacOS/Google Chrome Helper (Renderer)")
SHELL = f"{HOME}/Library/Caches/ms-playwright/chromium_headless_shell-1200/chrome-mac/headless_shell"
# The user's own Chrome (no marker), an orphaned MCP-launched Chrome with a busy renderer, an
# orphaned Playwright headless shell at near-zero CPU, an idle orphaned MCP server, and a
# marked browser whose MCP server is still alive.
BROWSERS = f"""\
40000     1 40000 {UID}    05:00:00    0:30.00 400000 {CHROME} --no-startup-window
40001 40000 40000 {UID}    05:00:00    0:20.00 200000 {HELPER} --type=renderer
41000     1 41000 {UID}    00:10:00    0:02.00 150000 {CHROME} --remote-debugging-pipe --user-data-dir=/var/folders/ab/T/puppeteer_dev_profile-x
41001 41000 41000 {UID}    00:10:00    3:00.00 250000 {HELPER} --type=renderer
41002 41000 41000 {UID}    00:10:00    0:30.00  90000 {HELPER} --type=gpu-process
42000     1 42000 {UID}    00:03:00    0:00.50  60000 {SHELL} --headless --remote-debugging-pipe
43000     1 43000 {UID}    00:30:00    0:00.20  30000 node {HOME}/.npm/_npx/abc/node_modules/.bin/mcp-server-playwright --isolated
44000 43500 44000 {UID}    00:30:00    0:05.00 100000 {CHROME} --remote-debugging-pipe --user-data-dir=/tmp/mcp-profile
43500  5662 43500 {UID}    00:30:00    0:01.00  30000 node {HOME}/.npm/_npx/def/node_modules/chrome-devtools-mcp/build/index.js
"""


def run(event: str, state: Path, listing: str = LISTING) -> subprocess.CompletedProcess:
    ps = state / "ps.txt"
    ps.write_text(listing)
    payload = {"hook_event_name": event, "session_id": "t", "source": "startup"}
    env = {**os.environ, "REAPER_PS_FILE": str(ps), "REAPER_STATE_DIR": str(state),
           "REAPER_SEEN_FILE": str(state / "seen.json")}
    return subprocess.run([sys.executable, str(TARGET)], input=json.dumps(payload), env=env,
                          capture_output=True, text=True, timeout=10)


class ReaperCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        (self.state / "reaper-ignore").write_text("# daemons I run on purpose\nignored-daemon.py\n")

    def tearDown(self):
        self.tmp.cleanup()

    def reported(self, proc: subprocess.CompletedProcess) -> str:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"] if proc.stdout else ""

    def test_session_start_reports_the_right_set(self):
        text = self.reported(run("SessionStart", self.state))
        self.assertIn("pid 9665 (orphaned", text)        # the Nov 14 leftover
        self.assertIn("pid 7001 (long-running", text)    # a session's three-hour job
        self.assertIn("pid 8200 (orphaned", text)        # 3 GB resident with no owner
        self.assertIn("pid 22169 (hog", text)            # a renderer spinning ~36% for 19 hours
        for quiet in ("2627", "pid 700 ", "22153", "7100", "5662", "7002", "8000", "8100"):
            self.assertNotIn(f"pid {quiet.strip()} (", text, quiet)
        # 22153 is the same app's idle parent; 7100 is busy but under an hour old.

    def test_agent_browsers_and_their_mcp_servers(self):
        text = self.reported(run("SessionStart", self.state, LISTING + BROWSERS))
        self.assertIn("pid 41000 (orphaned agent browser", text)
        self.assertIn("kill -TERM -41000", text)
        self.assertIn("3 min of CPU", text)                   # 2 s + 180 s + 30 s, summed over the group
        self.assertIn("pid 42000 (orphaned agent browser", text)   # a headless shell at almost no CPU
        self.assertIn("pid 43000 (orphaned browser MCP", text)     # idle and small, still reported
        for quiet in ("40000", "40001", "41001", "41002", "44000", "43500"):
            self.assertNotIn(f"pid {quiet} (", text, quiet)
        # 40000 is the user's own Chrome; 41001 and 41002 are counted under 41000;
        # 44000's MCP server 43500 is alive under a session.

    def test_group_stop_only_for_a_private_group(self):
        # Marked orphans that do not lead a private group: one in the session's group, one in
        # its own launcher's leftover group, one claiming pgid 1. Each is reported by pid alone.
        listing = LISTING + (
            f"45000     1  5662 {UID}    00:10:00    0:01.00  90000 {CHROME} --remote-debugging-pipe\n"
            f"45100     1 45099 {UID}    00:10:00    0:01.00  90000 {CHROME} --remote-debugging-pipe\n"
            f"45101 45100 45099 {UID}    00:10:00   50:00.00  90000 {HELPER} --type=renderer\n"
            f"45200     1     1 {UID}    00:10:00    0:01.00  90000 {CHROME} --remote-debugging-pipe\n")
        text = self.reported(run("SessionStart", self.state, listing))
        for pid in ("45000", "45100", "45200"):
            self.assertIn(f"pid {pid} (orphaned agent browser", text)
        for group in ("-5662", "-45099", "-1"):
            self.assertNotIn(f"kill -TERM {group}", text)
        self.assertIn("pid 7001 (long-running", text)   # the other checks still run
        self.assertIn("marked by --remote-debugging-pipe", text)

    def test_text_masks_home_and_tokens(self):
        text = self.reported(run("SessionStart", self.state))
        self.assertNotIn(HOME, text)
        for secret in SECRETS:
            self.assertNotIn(secret, text)
        self.assertIn("[masked]", text)
        self.assertIn("untrusted data", text)
        self.assertIn("Do not stop any of them without the user's yes", text)

    def test_short_flag_secrets_are_masked(self):
        # Stand-ins in the detector's all-x placeholder form, as in SECRETS above.
        listing = LISTING + (f"31000     1 31000 {UID}    02:00:00  100:00.00  9000 mysql -uroot -ppw_xxxxxxxx db\n"
                             f"31001     1 31001 {UID}    02:00:00  100:00.00  9000 curl -u admin:pw_xxxxxxxx http://h/\n"
                             f"31002     1 31002 {UID}    02:00:00  100:00.00  9000 sshpass -p pw_xxxxxxxx ssh h\n")
        text = self.reported(run("SessionStart", self.state, listing))
        for pid in ("31000", "31001", "31002"):
            self.assertIn(f"pid {pid} (hog", text)
        self.assertNotIn("pw_xxxxxxxx", text)

    def test_bad_or_future_state_does_not_mute_the_check(self):
        seen = self.state / "seen.json"
        for bad in ("[1, 2]", '{"checked": 99999999999}', '{"checked": "x", "seen": 5}', "not json"):
            with self.subTest(bad=bad):
                seen.write_text(bad)
                self.assertIn("pid 22169 (hog", self.reported(run("UserPromptSubmit", self.state)))

    def test_prompt_checks_at_most_every_half_hour(self):
        first = self.reported(run("UserPromptSubmit", self.state))
        self.assertIn("pid 22169 (hog", first)
        self.assertEqual(run("UserPromptSubmit", self.state).stdout, "")   # inside the window

    def test_prompt_reports_only_what_no_check_reported(self):
        run("SessionStart", self.state)
        seen = self.state / "seen.json"
        state = json.loads(seen.read_text())
        self.assertTrue(any(k.startswith("22169:") for k in state["seen"]), state["seen"])
        state["checked"] -= 3600                                              # past the window
        seen.write_text(json.dumps(state))
        self.assertEqual(run("UserPromptSubmit", self.state).stdout, "")    # nothing new
        state = json.loads(seen.read_text())
        state["checked"] -= 3600
        seen.write_text(json.dumps(state))
        spinning = LISTING + f"30000     1 30000 {UID}    02:00:00  100:00.00  90000 /Applications/Viewer.app/Contents/MacOS/Viewer\n"
        text = self.reported(run("UserPromptSubmit", self.state, spinning))
        self.assertIn("pid 30000 (hog", text)
        self.assertNotIn("pid 22169", text)

    def test_report_mode_prints_plain_text(self):
        ps = self.state / "ps.txt"
        ps.write_text(LISTING)
        env = {**os.environ, "REAPER_PS_FILE": str(ps), "REAPER_STATE_DIR": str(self.state)}
        p = subprocess.run([sys.executable, str(TARGET), "--report"], env=env, capture_output=True,
                           text=True, timeout=10)
        self.assertEqual(p.returncode, 0)
        self.assertTrue(p.stdout.startswith("reaper: 4 heavy process(es)"), p.stdout)
        self.assertIn("pid 9665", p.stdout)
        ps.write_text(LAUNCHD)
        p = subprocess.run([sys.executable, str(TARGET), "--report"], env=env, capture_output=True,
                           text=True, timeout=10)
        self.assertEqual(p.stdout.strip(), "reaper: clean")

    def test_clean_machine_is_silent(self):
        p = run("SessionStart", self.state, LAUNCHD)
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_other_events_and_bad_input_fail_open(self):
        self.assertEqual(run("PreToolUse", self.state).stdout, "")
        p = subprocess.run([sys.executable, str(TARGET)], input="not json", capture_output=True,
                           text=True, timeout=10)
        self.assertEqual((p.returncode, p.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
