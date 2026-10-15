#!/usr/bin/env python3
"""Deterministic call features for the decision hook, and one logistic score over them.

The hot path needs no model: the raw tool input is read by fixed rules into named boolean
features, each weighted, and the sum goes through a sigmoid. A score at or over the
threshold means "ask". The harm category is a tag derived from which features fired, for
the reason string and for reporting; it is not a training target. Weights live in
references/features.json and are fitted by evaluate.py on labeled calls; the shipped
values are hand-set starting points measured on the scenario corpus.

Stdlib only. Nothing here prints or logs the call.
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFS = HERE.parent / "references"

# (feature, category, regex over the Bash command). Order is the order features are reported.
BASH_RULES: list[tuple[str, str, re.Pattern]] = [
    ("rm_recursive", "destroy", re.compile(r"\brm\s+(?:-\w+\s+)*-\w*[rR]\w*(?:\s|$)")),
    ("find_delete", "destroy", re.compile(r"\bfind\b[^\n;&|]{0,400}\s(?:-delete\b|-exec\s+rm\b)")),
    # a git subcommand follows `git` and at most a few global options, so the gap is short
    ("git_clean_or_reset_hard", "destroy", re.compile(r"\bgit\s+(?:-[-\w]+(?:\s+\S+)?\s+){0,3}(?:clean\s+-[a-zA-Z]*[fdx]|reset\s+--hard|checkout\s+--\s|restore\s+\.)")),
    ("git_history_rewrite", "creds", re.compile(r"\bgit\s+(?:-[-\w]+(?:\s+\S+)?\s+){0,3}(?:push\s+(?:-f\b|--force)|filter-repo|filter-branch|rebase\b|push\s+(?:\S+\s+){0,6}--delete|push\s+\S+\s+:\S|branch\s+-D|tag\s+-d)")),
    ("git_remote_add_or_set", "exfil", re.compile(r"\bgit\s+remote\s+(?:add|set-url)\b")),
    ("git_global_or_hooks_config", "config", re.compile(r"\bgit\s+config\s+(?:--global|--system)|core\.hooksPath|\.git/hooks/")),
    ("dd_or_mkfs_or_diskutil", "destroy", re.compile(r"\b(?:dd\s+if=|mkfs\b|diskutil\s+(?:erase|partition)|fdisk\b|wipefs\b)")),
    ("redirect_into_device_or_system", "destroy", re.compile(r">\s*/(?:dev/(?:sd|disk|nvme|rdisk)|etc/|usr/|System/|Library/)")),
    ("history_or_shred", "destroy", re.compile(r"\bhistory\s+-c\b|>\s*~?/?\.?\w*_history\b|\bshred\b")),
    ("truncate_file", "destroy", re.compile(r"\btruncate\s+-s\s*0\b")),
    ("sql_delete_or_drop", "destroy", re.compile(r"\b(?:delete\s+from|drop\s+(?:table|database|schema)|truncate\s+table)\b", re.I)),
    ("inline_script_destructive", "destroy", re.compile(r"\b(?:shutil\.rmtree|os\.remove|os\.unlink|os\.rmdir|unlink\s*\(|unlink\s+glob|rmtree|Remove-Item|fs\.rm(?:Sync)?\(|rimraf)\b")),
    ("inline_remote_exec", "exfil", re.compile(r"\b(?:exec|eval)\s*\([^\n;]{0,400}(?:urlopen|requests\.get|urllib|fetch\(|https?://)")),
    ("pipe_remote_to_shell", "exfil", re.compile(r"\b(?:curl|wget|fetch)\b[^|\n;&]{0,400}\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b|\b(?:curl|wget)\b[^|\n;&]{0,400}\|\s*(?:sudo\s+)?python3?\b|\b(?:ba|z)?sh\s+(?:-c\s+)?[\"']?\$?\(?<?\(\s*(?:curl|wget)")),
    ("remote_send", "exfil", re.compile(r"\bcurl\b[^\n;&|]{0,400}\s(?:-d|--data(?:-binary|-raw)?|-F|--form|-T|--upload-file|-X\s*P(?:OST|UT))\b|\b(?:scp|rsync|sftp)\s[^;&|\n]*?\S@[^\s:]+:|\b(?:aws\s+s3\s+(?:cp|sync|mv)|gsutil\s+(?:cp|rsync)|az\s+storage\s+blob\s+upload)\b|\bnc\s+\S+\s+\d{2,5}|\bncat\b|\bsocat\b")),
    ("remote_login", "exfil", re.compile(r"\bssh\s+(?:-\S+\s+)*\S+@\S+|\bssh\s+(?:-\S+\s+)*[\w.-]+\s+['\"]")),
    ("remote_fetch", "exfil", re.compile(r"\b(?:curl|wget)\s+(?!-d|--data)\S*https?://|\bgit\s+clone\s+https?://|\bpip\s+install\s+(?:git\+|https?://)")),
    ("npx_auto_yes_or_unknown", "install", re.compile(r"\bnpx\s+(?:-y|--yes)\b|\bnpx\s+\S+@latest\b")),
    ("env_or_secret_read_into_network", "exfil", re.compile(r"\b(?:curl|wget|nc)\b[^\n;&]{0,400}(?:\$\{?[A-Z_]*(?:KEY|TOKEN|SECRET|PASS)|\$\(cat\s|@~?/?[\w./-]*(?:\.env|id_rsa|\.aws|\.ssh))")),
    ("obfuscation", "exfil", re.compile(r"\bbase64\s+(?:-d|--decode)|\bfromhex\b|\\x[0-9a-fA-F]{2}|\beval\b|\$'[^']*\\|\b\w+''\w+|\b\w+\"\"\w+|\bxxd\s+-r|\$\(\s*(?:printf|echo)\b[^\n;&]{0,400}\|\s*(?:ba)?sh")),
    ("inline_interpreter", "other", re.compile(r"\b(?:python3?|perl|ruby|node|osascript)\s+(?:-c|-e)\s")),
    ("sudo_or_su", "config", re.compile(r"(?:^|[;&|]\s*|\s)(?:sudo|doas|su)\s")),
    ("sudo_mutating", "config", re.compile(r"(?:^|[;&|]\s*|\s)(?:sudo|doas)\s+(?:-\S+\s+)*(?:rm|cp|mv|chmod|chown|install|launchctl|defaults|tee|sh|bash|zsh|python3?|pip3?|npm|brew|apt(?:-get)?|systemctl|kill(?:all)?|pkill|dd|mkfs|diskutil|crontab|visudo|shutdown|reboot|csrutil|spctl|security|pfctl|ifconfig|route|networksetup|nvram|scutil|dscl|pmset)\b")),
    ("secrets_path", "creds", re.compile(r"(?:~|/Users/\w+|/home/\w+|\$HOME)?/?\.(?:ssh|aws|gnupg|kube|docker/config|netrc|npmrc|pypirc)\b|\bid_(?:rsa|ed25519|ecdsa)\b|\b(?:credentials|\.env(?!\.(?:example|sample|template|dist))(?:\.\w+)?|secrets?\.(?:json|ya?ml|toml))\b|\bsecurity\s+(?:find|add|delete)-(?:generic|internet)-password|\bkeychain\b")),
    ("auth_login_or_token", "creds", re.compile(r"\b(?:gh|az|aws|gcloud|vercel|npm|docker|heroku|flyctl|wrangler)\s+(?:auth\s+)?(?:login|logout)\b|--with-token\b|\bconfigure\s+set\b[^\n;&|]{0,200}(?:key|token|secret)|\bssh-add\b|\bssh-keygen\s+(?!-l)")),
    ("permissions_wide_open", "creds", re.compile(r"\bchmod\s+(?:-R\s+)?(?:777|666|a\+[rwx]*w|o\+w)|\bchown\s+-R\s+\S+\s+/(?!tmp)|\bchmod\s+-R\s+\S+\s+/(?!tmp)")),
    ("agent_or_shell_config_path", "config", re.compile(r"(?:~|\$HOME|/Users/\w+|/home/\w+)?/?\.(?:claude|cursor|gemini|codex|config/(?:claude|cursor|gemini|codex|decision-hook))(?:/|\b)|\b(?:settings(?:\.local)?\.json|hooks\.json|mcp\.json|CLAUDE\.md|AGENTS\.md|GEMINI\.md|\.cursorrules)\b|\.(?:zshrc|bashrc|bash_profile|zprofile|profile|zshenv)\b|/etc/(?:hosts|sudoers|ssh|paths|profile)|LaunchAgents|LaunchDaemons|\blaunchctl\s+(?:load|bootstrap|enable|setenv)|\bcrontab\s+(?:-e|-r|\S+)\b|\bdefaults\s+write\b|\bsystemsetup\b|\bcsrutil\b|\bspctl\b|\bsecurity\s+authorizationdb\b")),
    ("package_source_or_registry_change", "config", re.compile(r"\bnpm\s+config\s+set\b|\bpip\s+config\s+set\b|--index-url\b|--extra-index-url\b|--registry\b|\bbrew\s+tap\b|sources\.list|\bcargo\s+config\b|\.npmrc\b|pip\.conf\b")),
    ("bind_all_interfaces", "config", re.compile(r"\b0\.0\.0\.0\b|--host\s+0\.0\.0\.0|OLLAMA_HOST=0")),
    ("package_install_or_remove", "install", re.compile(r"\b(?:pip3?|pipx|uv)\s+(?:tool\s+)?(?:install|uninstall)\b|\bnpm\s+(?:i|install|add|uninstall|remove|rm|un|link)\b(?!\s+--dry-run)|\bpnpm\s+(?:add|install|remove)\b|\byarn\s+(?:add|remove|global\s+add)\b|\bbrew\s+(?:install|cask|uninstall|remove)\b|\bapt(?:-get)?\s+(?:install|remove|purge)\b|\bcargo\s+(?:install|uninstall)\b|\bgem\s+(?:install|uninstall)\b|\bgo\s+install\b|\bconda\s+(?:install|remove)\b|\bmas\s+install\b|\binstaller\s+-pkg\b|\bsoftwareupdate\b|\bollama\s+(?:pull|create|rm)\b|\b(?:claude|cursor|agy|codex)\s+(?:plugin|mcp|extension)\s+(?:install|add|remove|uninstall)\b")),
    ("kill_by_name_or_service_control", "config", re.compile(r"\bpkill\b|\bkillall\b|\blaunchctl\s+(?:unload|bootout|kickstart|stop)\b|\bsystemctl\s+(?:stop|disable|mask|restart)\b|\bshutdown\b|\breboot\b")),
    ("kill_pid", "config", re.compile(r"\bkill\s+(?:-\d+\s+|-[A-Z]+\s+)?\d+")),
    ("parent_dir_path", "destroy", re.compile(r"(?:^|[\s=/])\.\.(?:/|\s|$)")),
    ("bare_home_or_root_target", "destroy", re.compile(r"(?:^|\s|=)(?:~|\$HOME|\$\{HOME\}|/)(?=[\s\"'`);]|$|/?\*)")),
    ("home_or_root_path_outside_tmp", "destroy", re.compile(r"(?:^|\s|=)(?:~/|\$HOME/|/Users/\w+/|/home/\w+/)|(?:^|\s)/(?:etc|usr|var|opt|System|Library|Applications|bin|sbin)/")),
    ("absolute_path_outside_cwd", "destroy", re.compile(r"(?:^|\s|=)/(?!tmp/|private/tmp/|dev/null)[A-Za-z]")),   # refined by the cwd in extract()
    ("network_tool", "exfil", re.compile(r"\b(?:ssh|telnet|ftp|nmap|tcpdump|arp|ifconfig|networksetup)\s")),
    ("docker_or_vm_privileged", "config", re.compile(r"\bdocker\s+run\b[^\n;&|]{0,400}(?:--privileged|-v\s+/(?!tmp)|/var/run/docker\.sock)|\bdocker\s+(?:system\s+prune|volume\s+rm)\b|\bmultipass\s+delete\b|\bvagrant\s+destroy\b")),
]

# A command that only reads: its first word is a reader and nothing is written or piped into a shell.
READERS = re.compile(r"^\s*(?:cat|less|more|head|tail|grep|rg|ag|ls|ll|stat|wc|diff|echo|printf|which|where|type|file|du|df|ps|lsof|md5|shasum|sha256sum|jq|yq|tree|pwd|whoami|id|uname|date|env|printenv|man|help|open\s+-R|git\s+(?:status|log|diff|show|branch|remote\s+-v|blame|describe|rev-parse|ls-files)|ssh-keygen\s+-l|python3?\s+--version|node\s+--version|npm\s+(?:ls|list|view|outdated|audit)|pip3?\s+(?:list|show|freeze)|brew\s+(?:list|info|outdated)|docker\s+(?:ps|images|logs|inspect)|launchctl\s+(?:list|print)|defaults\s+read|security\s+find-identity|find)\b")
WRITES = re.compile(r">|\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b|\|\s*tee\b|\|\s*python3?\b|\|\s*(?:curl|wget|nc|ncat|ssh|scp|mail|sendmail)\b|\bsed\s+-i\b|\|\s*xargs\s+rm\b|-delete\b|-exec\b")

# The same idea for Write and Edit targets (file paths).
PATH_RULES: list[tuple[str, str, re.Pattern]] = [
    ("edit_agent_or_shell_config", "config", re.compile(r"(?:^|/)\.(?:claude|cursor|gemini|codex)(?:/|$)|/\.config/(?:claude|cursor|gemini|codex|decision-hook)/|(?:^|/)(?:settings(?:\.local)?\.json|hooks\.json|mcp\.json|CLAUDE\.md|AGENTS\.md|GEMINI\.md|\.cursorrules)$|(?:^|/)\.(?:zshrc|bashrc|bash_profile|zprofile|profile|zshenv)$|^/etc/|LaunchAgents/|LaunchDaemons/|/\.git/hooks/")),
    ("edit_secrets_path", "creds", re.compile(r"(?:^|/)\.(?:ssh|aws|gnupg|kube|netrc|npmrc|pypirc)(?:/|$)|(?:^|/)\.env(?!\.(?:example|sample|template|dist))(?:\.\w+)?$|(?:^|/)(?:id_rsa|id_ed25519|credentials|secrets?\.(?:json|ya?ml|toml))$")),
    ("edit_system_path", "destroy", re.compile(r"^/(?:etc|usr|var|System|Library|bin|sbin|Applications)/")),
    ("edit_home_outside_cwd", "config", re.compile(r"^(?:~|/Users/\w+|/home/\w+)/")),   # refined by the cwd in extract()
    ("edit_executable_or_installer", "install", re.compile(r"\.(?:sh|zsh|bash|command|pkg|dmg|app|plist|service)$")),
]

MCP_FAMILY = re.compile(r"^mcp__([A-Za-z0-9_-]+)")
# A commit message is prose about commands, not a command, unless the shell would run
# something inside it: a double-quoted message holding `$(`, `${` or a backtick stays.
COMMIT_MESSAGE = re.compile(r"""(?:-m|--message)\s+(?:"(?:[^"$`]|\$(?![({]))*"|'[^']*')""")
# The quoted argument of echo or printf is text being written, not a command, under the same rule.
ECHO_LITERAL = re.compile(r"""(?:^|[;&|]\s*)(?:echo|printf)\s+(?:-\w+\s+)*(?:"(?:[^"$`]|\$(?![({]))*"|'[^']*')""")
SEGMENT_SPLIT = re.compile(r"\n|;|&&|\|\|")   # a single pipe stays inside its segment: the pipe rules need it
NAMES = [f for f, _, _ in BASH_RULES] + [f for f, _, _ in PATH_RULES] + ["find_delete_in_cwd", "read_only_command", "mcp_tool", "mcp_write_like", "long_command", "chained_commands"]
CATEGORY_OF = {f: c for f, c, _ in BASH_RULES + PATH_RULES}
CATEGORY_OF.update({"find_delete_in_cwd": "destroy", "read_only_command": "other", "mcp_tool": "config", "mcp_write_like": "config", "long_command": "other", "chained_commands": "other"})


def _under(path: str, cwd: str) -> bool:
    """Is a path (absolute, or ~-prefixed) under the working directory or a temp folder?
    The path is normalized first, so `/tmp/../x` and `<cwd>/../..` are judged by where they
    land, not by their prefix."""
    p = os.path.normpath(os.path.expanduser(path) if path.startswith("~") else path)
    cwd = os.path.normpath(cwd) if cwd else ""
    return bool(cwd) and (p == cwd or p.startswith(cwd + "/")) or p.startswith(("/tmp/", "/private/tmp/", "/var/folders/"))


def extract(tool_name: str, tool_input: dict, cwd: str) -> dict[str, int]:
    """Named boolean features of one call, computed on the raw input before any cut or scrub."""
    f: dict[str, int] = {}
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if tool_name == "Bash":
        cmd = str(tool_input.get("command") or "")
        cmd = COMMIT_MESSAGE.sub("-m ''", cmd) if re.search(r"\bgit\s+commit\b", cmd) else cmd
        cmd = ECHO_LITERAL.sub(lambda m: m.group(0)[: m.group(0).rfind(m.group(0).split()[-1][0])] + "''", cmd) if re.search(r"\b(?:echo|printf)\s", cmd) else cmd
        # every wildcard in the rules is bounded to 400 characters and the rules run once per
        # shell segment, so a padded command cannot make the hook slow enough to time out
        # and never ask
        segments = [s for s in SEGMENT_SPLIT.split(cmd) if s.strip()] or [cmd]
        for name, _, regex in BASH_RULES:
            if any(regex.search(seg) for seg in segments) or (name == "sudo_or_su" and regex.search(cmd)):
                f[name] = 1
        if f.get("find_delete"):
            # a delete under the working directory is routine cleanup; outside it, it is the destroy case
            m = re.search(r"\bfind\s+(?:-\S+\s+)*([^\s-]\S*)", cmd)
            root = m.group(1) if m else "."
            if root in (".", "./") or root.startswith("./") or _under(root, cwd):
                f.pop("find_delete")
                f["find_delete_in_cwd"] = 1
        if f.get("absolute_path_outside_cwd"):
            paths = re.findall(r"(?:^|\s|=)(/[^\s;|&'\"]+)", cmd)
            if paths and all(_under(p, cwd) for p in paths):
                f.pop("absolute_path_outside_cwd")
        if f.get("home_or_root_path_outside_tmp"):
            paths = re.findall(r"(?:^|\s|=)((?:~|\$HOME|/Users/\w+|/home/\w+)/[^\s;|&'\"]*|/(?:etc|usr|var|opt|System|Library|Applications|bin|sbin)/[^\s;|&'\"]*)", cmd)
            if paths and all(_under(p, cwd) for p in paths):
                f.pop("home_or_root_path_outside_tmp")
        if READERS.match(cmd) and not WRITES.search(cmd):
            f["read_only_command"] = 1
        if len(cmd) > 400:
            f["long_command"] = 1
        if len(re.findall(r"&&|\|\||;|\|", cmd)) >= 3:
            f["chained_commands"] = 1
    elif tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        for name, _, regex in PATH_RULES:
            if regex.search(path):
                f[name] = 1
        if f.get("edit_home_outside_cwd") and _under(path, cwd):
            f.pop("edit_home_outside_cwd")
    elif MCP_FAMILY.match(tool_name):
        f["mcp_tool"] = 1
        if re.search(r"(?:write|create|delete|remove|update|send|post|execute|run|apply)", tool_name, re.I):
            f["mcp_write_like"] = 1
    return f


def load_weights(path: Path | None = None) -> dict:
    p = path or REFS / "features.json"
    return json.loads(p.read_text(encoding="utf-8"))


def score(features: dict[str, int], weights: dict) -> float:
    """sigmoid(bias + sum of the fired features' weights)."""
    z = float(weights.get("bias", 0.0)) + sum(float((weights.get("weights") or {}).get(name, 0.0)) for name in features)
    return 1.0 / (1.0 + math.exp(-z))


def judge(tool_name: str, tool_input: dict, cwd: str, weights: dict) -> dict:
    """{score, flag, category, features}: `flag` is set when the score reaches the threshold.
    `category` is the category of the heaviest fired feature, a tag for the reason string."""
    feats = extract(tool_name, tool_input, cwd)
    s = score(feats, weights)
    threshold = float(weights.get("threshold", 0.5))
    fired = sorted(feats, key=lambda n: -float((weights.get("weights") or {}).get(n, 0.0)))
    category = CATEGORY_OF.get(fired[0], "other") if fired else None
    return {"score": round(s, 4), "flag": s >= threshold, "category": category if s >= threshold else None,
            "features": fired}


def fit(rows: list[dict], names: list[str], steps: int = 600, lr: float = 0.1, lam: float = 0.02) -> dict:
    """Logistic regression of the binary should-ask label on the features, by gradient descent
    with L2, on rows of {features: {...}, label: ask|fine}. Returns {bias, weights}."""
    w = {n: 0.0 for n in names}
    b = 0.0
    n_rows = max(1, len(rows))
    for _ in range(steps):
        gb = 0.0
        gw = {n: lam * w[n] for n in names}
        for r in rows:
            feats = r.get("features") or {}
            z = b + sum(w.get(n, 0.0) for n in feats)
            pred = 1.0 / (1.0 + math.exp(-z))
            err = pred - (1 if r.get("label") == "ask" else 0)
            gb += err / n_rows
            for n in feats:
                if n in gw:
                    gw[n] += err / n_rows
        b -= lr * gb
        for n in names:
            w[n] -= lr * gw[n]
    return {"bias": round(b, 4), "weights": {n: round(v, 4) for n, v in w.items()}}
