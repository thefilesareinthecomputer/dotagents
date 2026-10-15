# Code review of <what: a change, a module, a feature>

<One or two sentences: what the files are, what they are for, and what changed or what question the review answers. State the language, the runtime and any constraint the reviewer cannot see in the files (stdlib only, must stay offline, runs as a hook).>

# What a complete review covers

Answer each in turn, under its own heading, and say "none found" where that is the honest answer.

1. **Correctness.** List inputs that produce a wrong result, a crash, a hang or a silent no-op. For each, give the file and line, the input that triggers it, what happens, and what should happen.
2. **Security and safety.** Report anything that reads, writes, runs or sends more than the brief allows: path handling, symlinks, shell or subprocess construction, untrusted input reaching a command, a file or a model, secrets in output or logs, a check that fails open.
3. **Simplification.** Point out code that does the same thing twice, a branch that cannot run, an abstraction with one caller, or a dependency a stdlib call replaces. Raise one only where the simpler form is shorter and no less clear.
4. **Tests.** Name the cases the tests do not cover that the findings above need, and any test that passes without exercising the behavior it names.

# Severity

Mark every finding **blocking** (wrong output, data loss, a boundary crossed), **should-fix** (wrong in a case the code will meet) or **note** (worth knowing, no change required). Order the findings by severity, then by file.

# Out of scope

<What the reviewer should not spend words on: style, naming, formatting, anything a linter owns, features not in the files.>

# Files

<The list the user approved, one per line, each with one clause on why it is in.>
