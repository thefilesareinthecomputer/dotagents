#!/usr/bin/env python3
"""SessionStart and UserPromptSubmit hook: detect a plugin daemon restart storm.

A plugin that runs a shared daemon (claude-mem's worker is the one on this
machine) can enter a kill-and-respawn loop when a hook decides the running
daemon is stale on every event. Each respawn costs a process tree; left alone
for hours it exhausts memory and swap. This hook counts daemon starts in the
recent window of the plugin's own log and raises the alarm early.

SessionStart: over threshold prints a systemMessage for the user and
additionalContext for the model. Exit 0 either way.
UserPromptSubmit: over threshold exits 2, which blocks the prompt and shows
stderr to the user, until the storm stops or the user acknowledges it by
touching the ack file (silences the block for ACK_MINUTES).
A missing or unreadable log never blocks anything.

Environment overrides, mainly for tests:
  DAEMON_STORM_LOG_DIR      directory of worker logs (default ~/.claude-mem/logs)
  DAEMON_STORM_THRESHOLD    starts inside the window that count as a storm (default 5)
  DAEMON_STORM_WINDOW_MIN   window in minutes (default 5)
  DAEMON_STORM_ACK_FILE     ack file path (default ~/.claude/state/daemon-storm-ack)
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

START_MARKERS = ('Worker started', 'Worker version mismatch')
STAMP = re.compile(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
TAIL_BYTES = 2_000_000
ACK_MINUTES = 60


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def recent_starts(log_dir, window_min, now=None):
    """Count daemon start and mismatch lines stamped inside the window.

    Reads the tail of the two newest log files by mtime, since the log
    rotates daily on UTC and a window can straddle midnight.
    """
    now = now or datetime.now()
    stamped = []
    for path in Path(log_dir).glob('*.log'):
        try:
            stamped.append((path.stat().st_mtime, path))
        except OSError:
            continue
    logs = [path for _, path in sorted(stamped)]
    count = 0
    for path in logs[-2:]:
        try:
            with open(path, 'rb') as fh:
                fh.seek(max(0, path.stat().st_size - TAIL_BYTES))
                text = fh.read().decode('utf-8', 'replace')
        except OSError:
            continue
        for line in text.splitlines():
            if not any(marker in line for marker in START_MARKERS):
                continue
            match = STAMP.match(line)
            if not match:
                continue
            try:
                stamp = datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
            except ValueError:
                continue
            # A future-dated line must not count, or it never ages out.
            if 0 <= (now - stamp).total_seconds() <= window_min * 60:
                count += 1
    return count


def acknowledged(ack_file):
    try:
        return time.time() - os.stat(ack_file).st_mtime < ACK_MINUTES * 60
    except OSError:
        return False


def condition(count, window_min, log_dir):
    return (
        f'Plugin daemon restart storm: {count} worker starts or version-mismatch '
        f'kills in the last {window_min} minutes in {log_dir}. Each restart spawns '
        f'a process tree; left running this exhausts memory.'
    )


def for_user(count, window_min, log_dir, ack_file):
    """Remediation for the human. It names config changes, so it never goes
    to the model: the trigger is a line count from a plugin-writable log."""
    return (
        condition(count, window_min, log_dir) +
        f' Stop it before doing anything heavy: check the newest log there for '
        f'the cause, compare the plugin manifest version with what the daemon '
        f'reports, and if it is a bad release disable the plugin and restart. '
        f'To work through the block deliberately, run '
        f'mkdir -p {ack_file.parent} && touch {ack_file} '
        f'(silences it for {ACK_MINUTES} minutes).'
    )


def for_model(count, window_min, log_dir):
    return (
        condition(count, window_min, log_dir) +
        ' Report this to the user and do nothing heavy until they answer. Do not '
        'change plugin configuration, settings, or hooks without the user\'s '
        'instruction in their own turn.'
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    event = payload.get('hook_event_name', '')
    log_dir = Path(os.environ.get('DAEMON_STORM_LOG_DIR',
                                  Path.home() / '.claude-mem' / 'logs'))
    ack_file = Path(os.environ.get('DAEMON_STORM_ACK_FILE',
                                   Path.home() / '.claude' / 'state' / 'daemon-storm-ack'))
    threshold = _env_int('DAEMON_STORM_THRESHOLD', 5)
    window_min = _env_int('DAEMON_STORM_WINDOW_MIN', 5)
    if not log_dir.is_dir():
        return 0
    try:
        count = recent_starts(log_dir, window_min)
    except OSError:
        return 0
    if count < threshold:
        return 0
    if event == 'UserPromptSubmit' and not acknowledged(ack_file):
        print(for_user(count, window_min, log_dir, ack_file), file=sys.stderr)
        return 2
    print(json.dumps({
        'systemMessage': for_user(count, window_min, log_dir, ack_file),
        'hookSpecificOutput': {
            'hookEventName': event or 'SessionStart',
            'additionalContext': for_model(count, window_min, log_dir),
        },
    }))
    return 0


if __name__ == '__main__':
    sys.exit(main())
