#!/usr/bin/env python3
"""Tests for the voice_reply.py UserPromptSubmit/Stop hook.
Target: the repo's specs/claude-code/hooks/voice_reply.py by default; HOOK_UNDER_TEST points
the run at a station copy such as ~/.claude/hooks/voice_reply.py.
Run: python3 tests/station-hooks/test-voice-reply.py   (or via unittest discover)

Contract: advisory only, exit 0 on every path, silent unless the session is an
interactive terminal one and ~/.claude/voice.json exists and says enabled. UserPromptSubmit
stops any playback and injects the spoken-summary instruction. Stop speaks only a <speak>
line that ends the reply, through the configured command, detached, with the text on stdin
and never in argv; a reply without one is silent. Fails open.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TARGET = Path(os.environ.get("HOOK_UNDER_TEST") or Path(__file__).resolve().parents[2] / "specs" / "claude-code" / "hooks" / "voice_reply.py")

# Records each call as [argv after the command, stdin].
RECORDER = "import json, sys; open(sys.argv[1], 'a').write(json.dumps([sys.argv[2:], sys.stdin.read()]) + '\\n')"
STOP = [["--stop"], ""]


def said(text):
    return [[], text]


class VoiceReplyTest(unittest.TestCase):
    def setUp(self):
        # The hook reads ~/.claude/voice.json and nothing else, so the tests give it a home of its own.
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.calls = self.tmp / "calls.jsonl"
        self.config = self.tmp / ".claude" / "voice.json"
        self.config.parent.mkdir()

    def configure(self, enabled=True):
        self.config.write_text(json.dumps({
            "enabled": enabled,
            "command": [sys.executable, "-c", RECORDER, str(self.calls)],
        }))

    def env(self, **extra):
        return dict(os.environ, HOME=str(self.tmp), **extra)

    def run_hook(self, payload, raw=None, entrypoint="cli", **extra):
        data = raw if raw is not None else json.dumps(payload)
        return subprocess.run([sys.executable, str(TARGET)], input=data, text=True, capture_output=True,
                              env=self.env(CLAUDE_CODE_ENTRYPOINT=entrypoint, **extra), timeout=10)

    def stop(self, message):
        return self.run_hook({"hook_event_name": "Stop", "last_assistant_message": message})

    def recorded(self, expect=1):
        deadline = time.time() + 5
        while time.time() < deadline:
            if self.calls.exists():
                lines = self.calls.read_text().splitlines()
                if len(lines) >= expect:
                    return [json.loads(x) for x in lines]
            time.sleep(0.05)
        return [json.loads(x) for x in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def assert_silent(self):
        time.sleep(0.3)
        self.assertFalse(self.calls.exists(), self.calls.read_text() if self.calls.exists() else "")

    # --- off by default -------------------------------------------------

    def test_no_config_is_silent(self):
        r = self.stop("<speak>hi</speak>")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assert_silent()

    def test_disabled_is_silent(self):
        self.configure(enabled=False)
        r = self.run_hook({"hook_event_name": "UserPromptSubmit"})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assert_silent()

    def test_headless_run_is_silent(self):
        self.configure()
        for event in ("UserPromptSubmit", "Stop"):
            r = self.run_hook({"hook_event_name": event, "last_assistant_message": "<speak>hi</speak>"},
                              entrypoint="sdk-cli")
            self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assert_silent()

    def test_the_config_path_cannot_be_redirected_by_the_environment(self):
        # An environment variable naming another config would let whoever sets the hook's
        # environment pick the command every session runs.
        other = self.tmp / "elsewhere.json"
        other.write_text(json.dumps({"enabled": True, "command": [sys.executable, "-c", RECORDER, str(self.calls)]}))
        r = self.run_hook({"hook_event_name": "Stop", "last_assistant_message": "<speak>hi</speak>"},
                          CLAUDE_VOICE_CONFIG=str(other))
        self.assertEqual(r.returncode, 0)
        self.assert_silent()

    # --- UserPromptSubmit -----------------------------------------------

    def test_prompt_stops_playback_and_injects_instruction(self):
        self.configure()
        r = self.run_hook({"hook_event_name": "UserPromptSubmit"})
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        self.assertIn("<speak>", out["additionalContext"])
        self.assertEqual(self.recorded(), [STOP])

    # --- Stop -----------------------------------------------------------

    def test_stop_speaks_only_the_speak_line(self):
        self.configure()
        r = self.stop("Long reply with `code` and a path.\n\n```\nls\n```\n<speak>The card is flashed. Plug in the Pi.</speak>")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(self.recorded(), [said("The card is flashed. Plug in the Pi.")])

    def test_stop_strips_markdown_marks_but_keeps_underscores_inside_words(self):
        self.configure()
        r = self.stop("<speak>Run **step one** in `voice_reply` and _then_ wait.</speak>")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.recorded(), [said("Run step one in voice_reply and then wait.")])

    def test_only_a_speak_line_that_ends_the_reply_is_spoken(self):
        # A tag quoted from a file mid-reply never speaks, even when the reply ends with its own.
        self.configure()
        self.stop("The file says <speak>quoted text</speak> in its docs.\n\n<speak>Done, nothing needed.</speak>\n")
        self.assertEqual(self.recorded(), [said("Done, nothing needed.")])

    def test_a_reply_whose_speak_tag_is_not_last_is_silent(self):
        self.configure()
        self.stop("The file says <speak>quoted text</speak> and the reply goes on.")
        self.assert_silent()

    def test_a_reply_without_a_speak_line_is_silent(self):
        self.configure()
        for message in ("Fifteen paragraphs of detail.", "<speak>  </speak>"):
            r = self.stop(message)
            self.assertEqual(r.returncode, 0)
        r = self.run_hook({"hook_event_name": "Stop", "transcript_path": "/nonexistent.jsonl"})
        self.assertEqual(r.returncode, 0)
        self.assert_silent()

    def test_speak_line_never_reaches_the_speakers_argv(self):
        # argv is visible to every local account in ps and could be read as an option; stdin is neither
        self.configure()
        for line in ("--output-file=/tmp/x", "--stop", "— -v hi"):
            self.calls.unlink(missing_ok=True)
            self.stop(f"<speak>{line}</speak>")
            self.assertEqual(self.recorded(), [said(line)])

    def test_speak_line_is_bounded_and_has_no_control_characters(self):
        self.configure()
        self.stop("<speak>a\x00b " + "x" * 2000 + "</speak>")
        ((argv, text),) = self.recorded()
        self.assertEqual(argv, [])
        self.assertLessEqual(len(text), 400)
        self.assertNotIn("\x00", text)

    def test_stop_returns_before_speech_finishes(self):
        self.config.write_text(json.dumps({"enabled": True, "command": [sys.executable, "-c", "import time; time.sleep(5)"]}))
        start = time.time()
        r = self.stop("<speak>hi</speak>")
        self.assertEqual(r.returncode, 0)
        self.assertLess(time.time() - start, 3)

    # --- the /voice toggle ----------------------------------------------

    def toggle(self, *args):
        return subprocess.run([sys.executable, str(TARGET), *args], text=True,
                              capture_output=True, env=self.env(), timeout=10)

    def test_toggle_flips_enabled_keeps_the_command_and_says_so(self):
        self.configure(enabled=False)
        self.config.chmod(0o600)
        before = json.loads(self.config.read_text())["command"]
        r = self.toggle("on")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "Voice is on."))
        cfg = json.loads(self.config.read_text())
        self.assertEqual((cfg["enabled"], cfg["command"]), (True, before))
        self.assertEqual(self.recorded(), [said("Voice is on.")])  # heard at once, before any reply
        self.assertIn("Voice is on", self.toggle("status").stdout)
        self.assertIn("interactive", self.toggle("status").stdout)  # claude -p stays silent; say so
        self.calls.unlink()
        r = self.toggle("off")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "Voice is off."))
        self.assertIs(json.loads(self.config.read_text())["enabled"], False)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.recorded(), [STOP])
        self.assertEqual(sorted(p.name for p in self.config.parent.iterdir()), ["voice.json"])

    def test_toggle_without_a_speaker_changes_nothing(self):
        r = self.toggle("on")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(self.config.exists())
        self.assertIn("Voice is off", self.toggle("status").stdout)

    def test_toggle_rejects_other_arguments(self):
        self.configure(enabled=False)
        for args in (["maybe"], ["on", "extra"], ["--stop"]):
            self.assertEqual(self.toggle(*args).returncode, 2)
        self.assertIs(json.loads(self.config.read_text())["enabled"], False)

    # --- fail open ------------------------------------------------------

    def test_malformed_input_exits_zero(self):
        self.configure()
        r = self.run_hook(None, raw="not json")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_bad_config_exits_zero(self):
        self.config.write_text("{broken")
        r = self.stop("<speak>hi</speak>")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_missing_command_exits_zero(self):
        self.config.write_text(json.dumps({"enabled": True, "command": ["/nonexistent/speaker"]}))
        r = self.stop("<speak>hi</speak>")
        self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
