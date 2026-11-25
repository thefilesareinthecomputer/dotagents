---
name: goldfish
description: >-
  goldfish is a fast cold read of a document before someone acts on it. A
  fresh-context reader subagent that has never seen the session reads the
  document and the files it names, and lists everything a newcomer would guess, every reference that does not resolve and every
  contradiction, so the session can fix the document. Most often that is a
  SPEC*.md and its tasks/ plan before implementation. It also covers a README,
  guide, runbook, handoff or any other documentation, checked against the code
  it describes: commands, flags, paths and behavior the doc claims that the code
  lacks or does differently. Use when the user asks to goldfish something; to
  pressure-test, sanity-check or hole-poke a spec, plan or doc; to ask whether a
  spec is ready to build from; or whether a README still matches the code. It
  takes a path or a few words naming the document. goldfish is not a substitute
  for PR reviews, security reviews, wrap up, etc.
argument-hint: "[fable|opus|sonnet|haiku] <spec, README or doc path, or a few words naming it>"
---

# goldfish

The session that wrote a document reads into it what it knows from its own
context. A reviewer with none of that context finds the gaps before an
implementer or a user does, or this session after a compaction, falls into them.

Specs in this repo's `tasks/` right now:

!`ls tasks/SPEC-*.md 2>/dev/null || echo "(no tasks/SPEC-*.md here)"`

## Procedure

1. **Find the document and its mode.** The argument is a path or a few words
   ("the agent team spec", "the code-kg README"). Match words against the spec
   list above, then against README.md, SKILL.md and docs files by name and title
   line. One clear match: use it and name it. More than one: ask with
   AskUserQuestion, listing the candidates. None: say so and stop.
   - **Spec mode:** a `SPEC*.md`, a plan or a handoff, read before it is built from.
   - **Doc mode:** a README, SKILL.md, guide, runbook or other documentation,
     read against the code it describes.
2. **Pick the model.** If the first word is `fable`, `opus`, `sonnet` or
   `haiku`, pass it as the Agent call's `model`. Otherwise pass none; the
   `reader` definition sets Sonnet. Say which model ran.
3. **Pick the files.** Beside the document, add as paths:
   - spec mode: the plan files that drive its implementation (the handoff or
     plan sections that name this spec or its phases, such as `tasks/todo.md`),
     and every code, config or test file the spec and those plans name;
   - doc mode: every code, config or script file the doc names by path, command,
     flag or function, resolved to a path. For a README, add the entry point of
     each command it documents, such as the CLI script and its argument parser.

   Files only, never the whole repo, and never `.env*`, keys or other
   credential files. State the list in one line before spawning.
4. **Spawn the `reader` subagent** with a brief that carries task content only,
   the file list and the task for the mode, and nothing from the session.

   Spec mode:

   > Read only these files. You will implement the spec from them alone,
   > starting tomorrow, with no one to ask. Report, each with its file and line:
   > 1. Every point where you would have to guess: a term used before it is
   >    defined, an "as before" or "the existing X" with no file named, a format
   >    or rule stated loosely.
   > 2. Every reference that does not resolve: a path, function, flag, command
   >    or format the docs name that the code does not have or has differently.
   > 3. Every contradiction, between the docs or between a doc and the code.
   > 4. The first step you would take, and anything blocking it.
   > Rank by how badly each would derail the build. Say plainly when a category
   > is empty. Do not suggest features or restyle prose.

   Doc mode:

   > Read only these files. You are new to this project and will use it from
   > this document alone, with no one to ask. Check the document against the
   > code. Report, each with its file and line:
   > 1. Every claim the code contradicts: a command, flag, path, default, output
   >    or behavior the document states that the code lacks or does differently.
   > 2. Every point where you would have to guess: a term used before it is
   >    defined, a step that assumes knowledge the document never gives, a
   >    prerequisite left out.
   > 3. Every reference that does not resolve: a link, path or file that does
   >    not exist.
   > 4. Anything a user runs that the code exposes and the document omits:
   >    commands and options only, not internals.
   > Rank by how badly each would mislead a user. Say plainly when a category
   > is empty. Do not suggest features or restyle prose.

5. **Fix the document, not the chat.** Answer each finding by editing the
   document so the answer is written down; dismiss one only with a reason.
   Check a finding against the files before acting on it, since the reader can
   misread too. When the code is wrong rather than the document, report it to
   the user instead of editing the code. Rerun once on the edited files, and
   stop when a pass finds nothing that would derail the build or mislead a
   user. Report what changed in a few lines.
