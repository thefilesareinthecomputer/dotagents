# Interactive programs: prompts, shells and full-screen interfaces

Read this for a program that holds a session with the user: a prompt loop, a chat or agent shell, or a full-screen terminal interface.
`standard.md` still applies to how such a program is started, configured and scripted.

Support for these rules is thinner than for `standard.md`. The research found one project recipe on restoring the terminal (Ratatui's, known through a summary); the rest is practice. Tags are as in `standard.md`.

Three terms used below:

- **Raw mode:** the terminal passes each key to the program at once, with no line editing and no signals from control keys.
- **Alternate screen:** a second screen buffer a full-screen program draws on; leaving it brings back what was on the terminal before.
- **Bracketed paste:** a mode in which the terminal marks pasted text, so the program can tell a paste from typing.

## A session program is also a command

- Give it a one-shot mode: a flag that takes the input, prints the answer to stdout and exits. Scripts and agents use that mode. `[house]`
- With stdin not a terminal, read the input from stdin and run once, or fail with the flag to pass. Never start the prompt loop. `[house]`
- `--help`, `--version` and a bad flag behave as in `standard.md` and never enter the session. `[house]`

## Keys the user already knows

- Ctrl-C stops the thing in progress and returns to the prompt. It does not end the session. `[practice]`
- At an empty prompt, Ctrl-C clears the line, and a second one in a row says how to quit or quits. `[practice]`
- Ctrl-D on an empty line ends the session. `[practice]`
- Up and down recall history; the line-editing keys of the platform's line editor work. `[practice]`
- A way to enter several lines exists and is named in the help. `[house]`
- A `help` command, or `/help`, lists what can be typed. `[house]`

In raw mode the terminal delivers Ctrl-C as byte 0x03 and Ctrl-D as 0x04; no signal arrives and no end-of-file is seen. The program must read and act on them itself. `[practice]`

## Stopping work in progress

- An interrupt reaches the running operation and its child processes, within a second. `[house]`
- After an interrupt, say what state things are in. When it is unknown whether an action completed, say exactly that, so nobody retries it blindly. `[house]`
- A time limit that ends an operation reports itself as a time limit, with the limit's value. `[house]`

## The terminal is borrowed

- Restore it on every exit: normal quit, error, Ctrl-C, SIGTERM and SIGHUP. Leave raw mode, leave the alternate screen, show the cursor, turn off mouse and bracketed-paste modes. `[practice]`
- Install the restore before changing any mode, and call the previous handler after. `[practice]`
- Cleanup that runs when an error propagates (a `finally` block, a destructor, a crash hook) does not run when SIGTERM or SIGHUP ends the process. Install handlers for those signals that restore the terminal and then exit. `[practice]`
- Use the alternate screen only for a full-screen interface. A prompt loop writes to the normal screen, so the session stays in the scrollback. `[house]`

## Output while it streams

- Flush as text arrives. A reply that appears all at once after a long wait reads as a hang. `[house]`
- Show that work is happening within about a tenth of a second, and show what: the step, the tool, the file. `[clig]` `[house]`
- Keep the user's result visually apart from the program's own notes about the run. `[house]`
- Respect the terminal's width, and reflow on resize in a full-screen interface. `[practice]`
- When the output is not a terminal, or `TERM=dumb`, write plain lines with no cursor movement. `[clig]`

## State across sessions

- History lives in the state directory (`standard.md`, section 11), created with mode 0700. `[xdg]` Session files go there too. `[house]`
- Never write a secret to history. `[house]`
- A session can be resumed, and a file cut short by a crash is recovered or skipped with a notice; it never blocks startup. `[house]`
- Before quitting with work unsaved or still running, say so and ask once. `[house]`

## Testing

- Drive the program through a pseudo-terminal; pipes cannot show terminal behavior. `[practice]`
- Test each exit: quit, Ctrl-C mid-operation, SIGTERM, and the parent going away. After each, assert that the terminal modes are restored and no child process is left. `[house]`
- `cli_probe.py` checks only the command surface. Add `--no-args` to confirm the bare program returns when stdin is closed.
