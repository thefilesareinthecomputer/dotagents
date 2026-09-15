#!/usr/bin/env python3
"""PreToolUse, UserPromptSubmit, and SessionStart hook: gate on memory pressure.

Reads the kernel's own memory verdict (the level behind Activity Monitor's
pressure graph) plus swap in use, and stops the agent from adding load when
the machine is already struggling, whatever the cause.

Severity: critical is the kernel's critical level only. Warn is the kernel's
warn level, or swap in use at or above half of physical memory (swap is
sticky on macOS and never shrinks on its own, so it can raise a question but
never a lockout).

PreToolUse on load-adding tools (Bash, Agent, Workflow, any MCP tool):
  warn     -> permission "ask": the user decides
  critical -> permission "deny", or "ask" when the ack file is fresh
UserPromptSubmit: critical exits 2 (blocks the prompt, stderr to the user)
  unless the ack file is fresh, in which case the prompt passes silently;
  warn passes with a warning.
SessionStart: warn or critical prints a warning, never blocks.
Any other tool, a normal reading, or a machine without sysctl: silent exit 0.

The hook takes no containment action and tells the model to take none. The
user-facing text names the top processes by memory; the model-facing text
carries only the numbers and an instruction to stop and wait for the user.
This is a resource guard, not a security control: the environment overrides
below can switch it off, and that is acceptable.

Environment overrides:
  MEMGATE_PRESSURE_LEVEL  force the kernel level (1 normal, 2 warn, 4 critical)
  MEMGATE_SWAP_MB         force swap in use, megabytes
  MEMGATE_SWAP_ASK_MB     swap that asks (default half of physical memory)
  MEMGATE_ACK_FILE        ack file (default ~/.claude/state/memory-gate-ack);
                          touching it eases the gate for ACK_MINUTES
  BRAIN_SEAT              set by the second-brain spawner on a seat's process:
                          every gated call is denied outright (no prompt is
                          possible headless) with a "brain-gate: memory-pressure"
                          reason prefix the spawner attributes, ack or not
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ACK_MINUTES = 60
SYSCTL_TIMEOUT = 1
PS_TIMEOUT = 1
SYSCTL = '/usr/sbin/sysctl'
SYSCTL_KEYS = ('kern.memorystatus_vm_pressure_level', 'kern.memorystatus_level',
               'vm.swapusage', 'hw.memsize')
GATED_TOOLS = ('Bash', 'Agent', 'Workflow')
GATED_PREFIXES = ('mcp__',)
SAFE_NAME = re.compile(r'[^A-Za-z0-9 ._()/-]')


@dataclass(frozen=True)
class Signals:
    level: int
    free_pct: int
    swap_mb: int
    mem_mb: int


@dataclass(frozen=True)
class Config:
    warn_level: int = 2
    crit_level: int = 4
    swap_ask_mb: int = 0          # 0 means half of physical memory
    gated_tools: tuple = GATED_TOOLS
    gated_prefixes: tuple = GATED_PREFIXES


@dataclass(frozen=True)
class Decision:
    action: str
    user_text: str = ''
    model_text: str = ''


def sanitize(name):
    """Process names are attacker-choosable; keep them printable and short."""
    return SAFE_NAME.sub('', str(name))[:40]


def parse_swap_mb(line):
    match = re.search(r'used\s*=\s*([\d.]+)([MG])', line)
    if not match:
        return 0
    value, unit = float(match.group(1)), match.group(2)
    return int(value * 1024) if unit == 'G' else int(value)


def severity(sig, cfg):
    """'critical', 'warn', or '' with the reason that produced it."""
    if sig.level >= cfg.crit_level:
        return 'critical', f'kernel memory pressure level {sig.level} (critical)'
    if sig.level >= cfg.warn_level:
        return 'warn', f'kernel memory pressure level {sig.level} (warn)'
    ask_mb = cfg.swap_ask_mb or max(sig.mem_mb // 2, 1)
    if sig.swap_mb >= ask_mb:
        return 'warn', f'swap in use {sig.swap_mb} MB (warn)'
    return '', ''


def is_gated(tool, cfg):
    return tool in cfg.gated_tools or tool.startswith(cfg.gated_prefixes)


SEAT_PREFIX = 'brain-gate: memory-pressure'


def texts(sig, sev, reason, top, seat=None):
    numbers = (f'Memory pressure: {reason}, {sig.free_pct}% free, '
               f'{sig.swap_mb} MB swap.')
    procs = ', '.join(f'{sanitize(n)} {int(mb)} MB' for n, mb in top[:3])
    user = numbers + (f' Top processes: {procs}.' if procs else '') + (
        ' The agent adds no load until you decide. Close or stop what you '
        'can, then allow the call or answer the prompt.')
    if seat:
        # A headless seat has nobody to answer a prompt, so an ask would
        # be a silent deny. Say so, with a prefix the spawner can parse.
        model = (f'{SEAT_PREFIX}: {numbers} Load-adding calls are denied in '
                 f'seat {sanitize(seat)} while this lasts; no prompt is possible '
                 'headless. Report it and take no containment action of your own.')
        return user, model
    if sev == 'critical':
        guidance = (' Stop, report this to the user, and wait for the user. '
                    'Take no containment action of your own.')
    else:
        guidance = (' Report this to the user once. Read-only work may continue; '
                    'load-adding calls will ask the user first. Take no '
                    'containment action of your own.')
    return user, numbers + guidance


def decide(event, tool, sig, cfg, top=(), acked=False, seat=None):
    sev, reason = severity(sig, cfg)
    if not sev:
        return Decision('allow')
    user, model = texts(sig, sev, reason, top, seat)
    if event == 'PreToolUse':
        if not is_gated(tool, cfg):
            return Decision('allow')
        if seat:
            return Decision('deny', user, model)
        if sev == 'critical' and not acked:
            return Decision('deny', user, model)
        return Decision('ask', user, model)
    if event == 'UserPromptSubmit':
        return Decision('block' if sev == 'critical' else 'warn', user, model)
    return Decision('warn', user, model)


def _sysctl_all(keys):
    return subprocess.run([SYSCTL, '-n', *keys], capture_output=True, text=True,
                          timeout=SYSCTL_TIMEOUT, check=True).stdout


def read_signals(env, run=_sysctl_all):
    """All four kernel numbers from one sysctl call, with env overrides.
    None when anything is unreadable, which the caller treats as no gate."""
    try:
        lines = run(SYSCTL_KEYS).splitlines()
        level = int(env.get('MEMGATE_PRESSURE_LEVEL') or lines[0])
        free_pct = int(lines[1])
        swap_mb = int(env['MEMGATE_SWAP_MB']) if 'MEMGATE_SWAP_MB' in env \
            else parse_swap_mb(lines[2])
        mem_mb = int(lines[3]) // (1024 * 1024)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None
    return Signals(level=level, free_pct=free_pct, swap_mb=swap_mb, mem_mb=mem_mb)


def top_processes():
    """Top three processes by resident memory, largest first."""
    try:
        out = subprocess.run(['/bin/ps', '-Amco', 'rss=,comm='], capture_output=True,
                             text=True, timeout=PS_TIMEOUT, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.splitlines()[:3]:
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            rows.append((Path(parts[1]).name, int(parts[0]) // 1024))
    return rows


def acknowledged(ack_file):
    try:
        return time.time() - os.stat(ack_file).st_mtime < ACK_MINUTES * 60
    except OSError:
        return False


def render(d, event):
    """Hook JSON. An ask reason is shown to the user, so it carries the
    process list; a deny reason and additionalContext go to the model, so
    they carry the numbers only."""
    out = {'systemMessage': d.user_text,
           'hookSpecificOutput': {'hookEventName': event}}
    spec = out['hookSpecificOutput']
    if d.action == 'ask':
        spec['permissionDecision'] = 'ask'
        spec['permissionDecisionReason'] = d.user_text
    elif d.action == 'deny':
        spec['permissionDecision'] = 'deny'
        spec['permissionDecisionReason'] = d.model_text
    else:
        spec['additionalContext'] = d.model_text
    return out


def _env_int(env, name, default):
    try:
        return max(0, int(env.get(name, default)))
    except ValueError:
        return default


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    env = os.environ
    event = payload.get('hook_event_name', '') or 'SessionStart'
    tool = str(payload.get('tool_name', '') or '')
    cfg = Config(swap_ask_mb=_env_int(env, 'MEMGATE_SWAP_ASK_MB', 0))
    ack_file = Path(env.get('MEMGATE_ACK_FILE',
                            Path.home() / '.claude' / 'state' / 'memory-gate-ack'))
    sig = read_signals(env)
    if sig is None or not severity(sig, cfg)[0]:
        return 0
    acked = acknowledged(ack_file)
    seat = env.get('BRAIN_SEAT') or None
    # No ps spawn on a struggling machine for a call that passes anyway,
    # and no process names for a seat: they land in a foreign repo's
    # conversation record.
    top = () if seat else (
        top_processes() if event != 'PreToolUse' or is_gated(tool, cfg) else ())
    d = decide(event, tool, sig, cfg, top=top, acked=acked, seat=seat)
    if d.action == 'allow':
        return 0
    if d.action == 'block':
        if acked:
            return 0
        hint = (f' To work through it deliberately, run mkdir -p '
                f'{shlex.quote(str(ack_file.parent))} && touch '
                f'{shlex.quote(str(ack_file))} (eases the gate for {ACK_MINUTES} minutes).')
        print(d.user_text + hint, file=sys.stderr)
        return 2
    print(json.dumps(render(d, event)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
