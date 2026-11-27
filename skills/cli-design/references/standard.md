# The command-line standard

Rules for a command-line program that people and other programs can both rely on.
Each rule carries a tag for how well it is supported; `sources.md` has the documents and dates.

| Tag | Meaning |
|---|---|
| `[clig]` | Command Line Interface Guidelines (clig.dev), a community guideline |
| `[posix]` `[gnu]` `[xdg]` `[no-color]` | The named standard or specification |
| `[practice]` | Widely done; no primary source was verified for it |
| `[house]` | Learned from building and operating command-line tools; not from a cited source |

A tag covers the sentence it follows.
Section names, without their numbers, match the `rule` field in `cli_probe.py` reports. The probe reports against sections 1, 3 to 7, 9 and 10; the others are checked by hand.

## Contents

1. help
2. arguments
3. streams
4. exit-codes
5. errors
6. color
7. interactivity
8. destructive actions
9. robustness
10. machine-output
11. configuration
12. secrets
13. programs called by agents

## 1. help

- `--help` and `-h` print help to stdout and exit 0. `[gnu]` `[clig]`
- `--version` prints the name and version on its first line to stdout and exits 0. `[gnu]`
- Lead the help with one or two examples. `[clig]`
- A call that is missing a required argument prints short help: a description, an example, and a pointer to `--help`. `[clig]` It goes to stderr, because the call failed. `[practice]`
- A program with subcommands lists them when called bare, and each subcommand answers `--help`. `[practice]`
- Help must not load the whole program. Parse arguments before heavy imports, network calls or model loads. `[house]`

## 2. arguments

- Prefer flags to positional arguments. `[clig]` One positional type is fine; two different ones are easy to swap. `[practice]`
- Every flag has a long form. `[gnu]` `[clig]` A short form is for flags used often. `[house]`
- Use the common names for common things: `-h/--help`, `--version`, `-q/--quiet`, `-d/--debug`, `-n/--dry-run`, `-f/--force`, `-o/--output`, `--json`, `--no-input`. `[clig]`
- `-v` is read as "verbose" by some tools and "version" by others, so use it with care. `[clig]` Spell out `--verbose` and `--version`. `[house]`
- Accept `--` as the end of options, and `-` for stdin or stdout where a file is expected. `[posix]`
- Reject an unknown flag. Never ignore it silently, and never guess. `[house]`
- Keep flags that others script against. Add a new flag instead of changing what an old one means. `[house]`

## 3. streams

- stdout carries the result: the thing a caller would pipe or save. `[clig]`
- stderr carries what is said about the run: messages, warnings, errors and logs. `[clig]` Progress and prompts go there too. `[practice]`
- A caller who redirects stdout to a file must still see errors, and the file must hold only the result. `[house]`
- Help and version that were asked for are results and go to stdout. Help shown because of a mistake goes to stderr. `[practice]`
- Exit quietly when the reader of a pipe goes away (`tool | head`). No stack trace for a broken pipe. `[practice]`

## 4. exit-codes

- 0 means the command did what was asked. Anything else means it did not. `[clig]`
- Use 2 for a usage error (bad flag, missing argument) and 1 for a failed run. `[practice]`
- Give a distinct code to each failure a caller would handle differently. `[clig]` List the codes in the help. `[practice]`
- Stay within 0 to 125. Shells use 126, 127 and 128 plus the signal number (130 for Ctrl-C, 143 for SIGTERM). `[practice]`
- The `sysexits.h` codes (64 to 78) are described as legacy by their own manual page; do not adopt them for a new tool. `[practice]`
- A partial success is a failure with its own code, and the message says what was done and what was not. `[house]`

## 5. errors

- An error says what went wrong, in the user's terms, and what to do next. `[clig]`
- Name the offending value: the flag, the path, the line. `[house]`
- For a mistyped command or flag, suggest the nearest match. Never run the suggestion without asking. `[clig]`
- A stack trace is for an unexpected fault, with a line on how to report it. `[clig]` A usage error never shows one. `[house]`
- Put the most important line last, where a terminal leaves the eye. `[clig]`
- Debug detail goes behind `--verbose` or `--debug`, on stderr. `[practice]`
- Report only what happened. A step that was skipped is reported as skipped, never as done. `[house]`

## 6. color

- Color and other terminal codes are written only when the stream is a terminal. Check stdout and stderr separately. `[clig]`
- A `NO_COLOR` variable that is set and not empty turns color off, whatever its value. `[no-color]`
- Also turn color off for `TERM=dumb` and a `--no-color` flag. `[clig]`
- Color adds emphasis; it never carries the only copy of a fact. `[house]`

## 7. interactivity

- Prompt only when stdin is a terminal. `[clig]`
- Everything a prompt asks for can also be given by a flag. `--no-input` turns prompts off, and a missing value then fails with the flag to pass. `[clig]`
- With stdin closed or piped, the program returns. It never waits for input nobody can give. `[house]`
- Animations appear only on a terminal. `[clig]` That covers spinners, progress bars and any cursor movement. `[practice]`
- Use a pager only when the output is a terminal. `[clig]`

## 8. destructive actions

- Sort each command by effect: reads, writes, or destroys. Say so in its help. `[practice]`
- Offer `-n/--dry-run` on a command with real consequences. `[clig]` Offering it on anything that writes is the safer default. `[house]` Print what would change in the same form the real run reports. `[house]`
- Confirm before destroying. On a terminal, ask; without one, require `-f/--force`. `[clig]` Many tools also accept `--yes` for the same purpose. `[practice]`
- Scale the confirmation to the damage. For something that cannot be undone, have the user type the name of the thing. `[clig]`
- Write only where the user pointed or where the program's own directories are (section 11). `[house]`

## 9. robustness

- Validate input early. `[clig]` Validate all of it before changing anything. `[house]`
- Say something within about a tenth of a second, before any network call. `[clig]`
- Show progress for anything long. `[clig]` Say what is running and how to stop it. `[house]`
- Every network call and every child process has a time limit, and the limit can be set. `[clig]` `[house]`
- On Ctrl-C, stop at once, say so, and bound the cleanup. If cleanup can be long, say what a second Ctrl-C does. `[clig]`
- A program that starts children stops them on every exit: return, error, Ctrl-C, SIGTERM, SIGHUP. `[house]`
- Running the same command twice is safe. A command that regenerates a file writes identical bytes the second time. `[house]`
- Expect to start after a run that never cleaned up. `[clig]` Detect stale locks and temp files and recover. `[house]`

## 10. machine-output

- Offer `--json` wherever a program might read the result. `[clig]` Write one JSON value, or one JSON object per line for a stream. `[practice]`
- With `--json`, stdout holds nothing else: no banner, no progress, no color. `[house]`
- Treat the JSON shape as a contract. Add fields; never rename or remove one without a version change. `[practice]`
- Sort output that has no natural order, so two runs can be compared. `[house]`
- Write times as ISO 8601 in UTC, and sizes and counts as plain numbers. `[house]`
- Offer `--quiet` to drop everything but the result. `[clig]`

## 11. configuration

- Precedence, highest first: flags, environment variables, project config, user config, system config. `[clig]`
- User files follow the XDG directories: config in `$XDG_CONFIG_HOME` (default `~/.config`), data in `$XDG_DATA_HOME` (`~/.local/share`), state such as history and logs in `$XDG_STATE_HOME` (`~/.local/state`), cache in `$XDG_CACHE_HOME` (`~/.cache`). Create a missing directory with mode 0700. `[xdg]`
- Environment variable names are uppercase letters, digits and underscores. `[clig]` They carry the program's prefix. `[practice]`
- Provide a command or flag that shows the settings in effect and where each came from. `[house]`
- Never edit a config file the program does not own without asking. `[clig]`

## 12. secrets

- Never take a secret as a flag value: it lands in the process list and the shell history. `[clig]`
- Avoid environment variables for secrets where a file, stdin or the system keychain will do. `[clig]`
- Never print a secret, in output, in an error, or with `--debug`. `[house]`

## 13. programs called by agents

No vendor or standards body has published guidance here; these rules come from practice and from 2025 to 2026 engineering write-ups. Treat them as `[practice]` and `[house]`.

- An agent is a caller with no terminal and no patience for a prompt. Sections 3, 7 and 10 are what it relies on.
- Bound the output. Cap a long result by default, and end it with a line naming the flag that returns the rest.
- An error names its fix as a command the caller can run next.
- Mark failures that are worth retrying apart from those that are not, by exit code or a field in the JSON.
- `--dry-run` output is structured, so a caller can check a plan before running it.
- Keep safety in the program. A rule that exists only in the documentation will be skipped by a caller that did not read it.
