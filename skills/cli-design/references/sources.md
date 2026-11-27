# Sources

Where the rules in `standard.md` and `interactive.md` come from, and how far each source was checked.
All pages were accessed 2026-11-27. Overall confidence is medium: the sources agree with each other, but several were read through search summaries.

## Read directly

| Source | What it supports | Notes |
|---|---|---|
| Command Line Interface Guidelines, https://clig.dev/ | Most `[clig]` rules: help, streams, errors, flags, prompts, robustness, configuration, secrets | A community guideline, not a standard. The page shows no update date. |
| NO_COLOR, https://no-color.org/ | The `NO_COLOR` rule | Page updated 2026-11-25; proposed 2017. |
| XDG Base Directory Specification 0.8, https://specifications.freedesktop.org/basedir/latest/ | Directory locations and mode 0700 | Dated 2021-05-08. |
| GitHub CLI manual, https://cli.github.com/manual/gh_help_formatting | `--json` with built-in filtering as a working example | |
| FreeBSD `sysexits(3)`, https://man.freebsd.org/cgi/man.cgi?query=sysexits&sektion=3 | `sysexits` described as legacy | One source for that wording. |

## Read through summaries only

| Source | What it supports |
|---|---|
| POSIX Utility Syntax Guidelines, https://pubs.opengroup.org/onlinepubs/9699919799/xrat/V4_xbd_chap12.html | `--` ends options; `-` means stdin or stdout. Guidelines 1 to 9, 11 and 12 were not captured. |
| GNU Coding Standards, https://www.gnu.org/prep/standards/standards.pdf (updated 2026-04-27) | `--help` and `--version` to stdout with exit 0; long options |
| 12 Factor CLI Apps, https://jdx.dev/posts/2018-10-08-12-factor-cli-apps/ (2018-10-08) | Flags over arguments, streams, XDG |
| Advanced Bash-Scripting Guide, https://tldp.org/LDP/abs/html/exitcodes.html | 126, 127 and 128 plus the signal number |
| Ratatui panic-hook recipe, https://www.ratatui.rs/recipes/apps/panic-hooks/ | Restoring the terminal in a full-screen program |

## Not verified against a primary source

Where one of these appears as a rule, it is tagged `[practice]`.

- Exit code 2 for a usage error. Common tools do it; no standard was found that requires it.
- 128 plus the signal number, from the Bash manual itself.
- How to handle a closed pipe.
- Prompt-loop conventions: Ctrl-D on an empty line, Ctrl-C at the prompt, history.
- When to use the alternate screen.
- Shell completion and manual pages. No rule covers them yet.
- Guidance on programs that agents call. Only engineering write-ups from 2025 to 2026 exist, and they agree on JSON to stdout, a no-prompt flag, and errors that carry a code, a retry hint and a fix.

## Published skills and tools reviewed for structure

No command-line design skill was found in Anthropic's public skills repository (19 skills listed). Other large collections were not checked.

| Project | What was taken from it |
|---|---|
| `steipete/agent-scripts`, `skills/create-cli` | Settle the command's design before any implementation; a short list of default conventions. License not shown on the page. |
| `x0c/agent-friendly-cli-skill` (MIT) | A routing `SKILL.md` over references, scripts and tests; safety belongs in the program, not its documentation. |
| `h3y6e/agent-skills`, `designing-cli` | Probe the built program from outside; label each command read, write or destructive. Known from a summary only. |
| `pyclig` (PyPI) | Automated help, exit-code and stream checks, for Python Click programs only. Known from a summary only. |

No general, language-independent checker for these conventions was found; `cli_probe.py` fills that gap.
