# Claude Code context topology, ontology, and team heuristics

A standard for what lives where in an enterprise Claude Code deployment, in three parts.
The **topology** is the map: the levels, the paths they occupy, what each mechanism costs to load, and how they layer when they collide.
The **ontology** is the sorting standard: which kind of context belongs in which mechanism, and the procedure for placing a block that does not obviously sort.
The **team heuristics** are how a group operates that structure together out of one repository, and what goes wrong when they do not.

Verified against Claude Code 2.1.233 and the official documentation as of 2026-08-14; the headless column and section against 2.1.259 by canary probe on 2026-09-02.
[`SPEC-CLAUDE-CODE.md`](SPEC-CLAUDE-CODE.md) is one opinionated station built on these mechanisms; this file is the general standard.

[the-sorting-grid](#the-sorting-grid)
[the-three-levels](#the-three-levels)
[headless-mode](#headless-mode)
[the-mechanisms](#the-mechanisms)
[sort-a-block-of-context](#sort-a-block-of-context)
[memory-and-retrieval](#memory-and-retrieval)
[the-repository-as-shared-source-of-truth](#the-repository-as-shared-source-of-truth)
[the-four-questions](#the-four-questions)
[file-path-reference](#file-path-reference)

---
## the-sorting-grid

Two questions place any piece of context you want to give Claude Code. The first picks a column in the grid below, the second picks a row.

**Who does it bind?** The whole organization, this repository, or you personally.

**When does it need to be in context?** Every session, only when certain files are open, only when a particular task runs, or never, because it is enforced rather than read, runs in its own context, or lives in another system.

The fourth column is not a fourth level. A headless session (`claude -p`, the mode every spawned or scheduled agent runs in) loads the same three levels from the same files. The column records what changes when nobody is at the keyboard: which entries are dropped, and the extra channel the spawner has. [headless-mode](#headless-mode) has the mechanics.

| When it needs to be in context | Org level | Project level | User level | Headless: what differs for a spawned session |
|---|---|---|---|---|
| Every session | Managed policy `CLAUDE.md`, or the `claudeMd` key in managed settings | The repository's `CLAUDE.md`, at the root or in `.claude/` | Your personal `~/.claude/CLAUDE.md` | Same files load. The spawner adds to them with `--append-system-prompt`, or replaces the default with `--system-prompt` |
| Only when certain files are open | A rules file shipped in a plugin | A path-scoped rule in `.claude/rules/`, or a `CLAUDE.md` inside that directory | A personal rule in `~/.claude/rules/` | Same (per the docs; not probed) |
| Only when a particular task runs | A plugin skill from an internal marketplace | A skill in `.claude/skills/`, committed with the code | A personal skill in `~/.claude/skills/` | Same; the spawner invokes one by putting `/<name>` in the prompt |
| Never: it is enforced rather than read | Managed settings, using `permissions.deny`, `sandbox`, and `allowManagedHooksOnly` | Hooks and permission rules in `.claude/settings.json` | Hooks and permissions in `~/.claude/settings.json`, or `.claude/settings.local.json` for one repository | Nothing can be approved: a tool with no allow rule is refused, not asked about. A never-trusted cwd drops the project `settings.json` allow entries only; its deny rules and hooks, and everything in `settings.local.json`, still apply. The spawner adds rules at command-line scope with `--allowedTools`, `--disallowedTools`, and `--permission-mode` |
| Never: it runs in its own context | A subagent shipped in a plugin | A subagent in `.claude/agents/` | A personal subagent in `~/.claude/agents/` | Same, foreground only; the turn ends when the reply ends, so background work is lost |
| Never: it lives in another system | An approved server list, or a deployed `managed-mcp.json` | A server declared in the repository's `.mcp.json` | A server you add yourself, recorded in `~/.claude.json` | A project `.mcp.json` server that was never approved interactively cannot be approved now; the spawner passes `--mcp-config`, with `--strict-mcp-config` to use only that (per the docs; not probed) |

A `CLAUDE.md` file is loaded in full into every request for the life of the session. A path-scoped rule is loaded when Claude opens a matching file. A skill contributes one line of description at startup and its full body only when it is used. The same content in each of those three places costs three different amounts, and only the first is charged on every unrelated request.

---
## the-three-levels

### Org level

Org-level configuration is deployed centrally by IT or a platform team, and reaches every session on every machine, in every repository. Managed values take precedence over user and project settings apart from a few security-sensitive exceptions, and managed policy `CLAUDE.md` cannot be excluded at all.

| Belongs here | Does not belong here |
|---|---|
| Security and compliance requirements every session must observe | Anything specific to one repository |
| Permission deny rules for tools, commands, and paths | Anything a team should be able to change for their own project |
| Sandbox settings and network domain allowlists | Personal workflow preferences |
| API provider, authentication method, and login organization | Long reference material, which belongs in a plugin skill |
| The approved model list and any version floor | Content the model can derive from the code |
| Which MCP servers and plugin marketplaces are permitted | |
| Coding standards that hold across every repository the company owns | |

Managed settings and a managed `CLAUDE.md` do different jobs. **Settings** are enforced by the client regardless of what the model decides. A managed **`CLAUDE.md`** is behavioral guidance the model reads and generally follows. If a rule must hold every time, it goes in settings, not in prose.

Delivery reaches devices four ways, in priority order: server-managed from the admin console, plist or registry policy, a file at the managed policy path, then the Windows user registry. Server-managed settings refresh hourly during active sessions. Array settings such as `permissions.allow` and `permissions.deny` merge across sources, so developers can extend a managed list but cannot remove from it.

For distributing content rather than policy, package skills, subagents, hooks, and MCP servers as a **plugin** in an internal marketplace. That is how the same setup reaches every team, and it carries version history that copying files between repositories does not. `strictPluginOnlyCustomization` blocks skills, agents, hooks, and MCP servers from user and project sources so they can only arrive through plugins or managed settings.

### Project level

Project-level configuration is committed to source control, so it reaches everyone who clones the repository.
It is therefore also the team level: everything a team shares deliberately lives in this column, and [the-repository-as-shared-source-of-truth](#the-repository-as-shared-source-of-truth) covers how a team operates it.

| Belongs here | Does not belong here |
|---|---|
| Build, test, and run commands for this repository | Personal preferences, even widely shared ones |
| Repository layout and where things live | Secrets, tokens, and personal environment URLs |
| Conventions that differ from the language or framework default | A directory listing or dependency list, which the model reads faster than you can maintain |
| Constraints of the form "never do X in this codebase" | General language or framework knowledge |
| Per-area conventions, scoped to the directories they govern | An architecture overview that restates what the code shows |
| Repeatable procedures, as skills | Reference material nobody reads in most sessions, unless it is a skill |
| Event automation, as hooks | |
| MCP servers this repository needs | |

Keep the project `CLAUDE.md` under 200 lines. Longer files consume more context and reduce adherence. Once it grows past that, move content out into a rule or a skill rather than trimming sentences.

In a monorepo, put repository-wide rules in the root `CLAUDE.md` and area-specific conventions in a `CLAUDE.md` inside each package or subsystem. Files from your working directory and every parent load at launch; files in subdirectories load when Claude reads a file there. Directory owners maintain their own file, and the files get reviewed in pull requests like any other documentation.

### User level

User-level configuration lives on your machine and applies to every project you open.

| Belongs here | Does not belong here |
|---|---|
| Personal workflow and formatting preferences | Anything a teammate needs to reproduce your result |
| Personal tooling shortcuts and aliases | Anything policy-bearing, which is an org decision |
| Skills you use across many repositories | Project conventions that others should inherit |
| Personal permission allowances that reduce prompting | |
| Per-project preferences that must not be committed, in `CLAUDE.local.md` | |

One test settles most cases. If a colleague who cloned the repository would get a worse answer from Claude because they do not have this instruction, it belongs at the project level instead.

### How the levels combine

Not all mechanisms layer the same way. Additive means every level's content is present at once. Override by name means one definition wins and the rest are ignored.

| Mechanism | Layering behavior |
|---|---|
| `CLAUDE.md` and rules | Additive. Every level contributes content simultaneously. Order runs broad to specific, so more specific instructions are read last. Conflicts are resolved by the model's judgment, which is a reason to remove contradictions rather than rely on ordering. |
| Skills | Override by name: managed, then user, then project. |
| Subagents | Override by name: managed, CLI flag, project, user, plugin. |
| MCP servers | Override by name: local, then project, then user. |
| Hooks | Merge. Every registered hook fires for its matching event regardless of source. |
| Settings | Highest scope wins, in this order: managed, command line, local, project, user. |
| Permission rules specifically | Across every scope, a matching deny beats a matching allow, and command line means `--allowedTools` / `--disallowedTools`. A flag allow cannot override a `settings.local.json` deny; a flag deny does override a `settings.local.json` allow (probed 2.1.259). |

Run `/context` to see what actually loaded in a session, and `/status` to confirm which managed settings source is active.

---
## headless-mode

Headless is `claude -p "<prompt>"`, also called print mode: one turn, no terminal, output to stdout, the process exits when the reply ends. Every agent that another program starts runs this way, whether that is CI, a cron job, a subagent-spawning orchestrator, or a chat app seating an agent in its own repository. Conceptually it is a different kind of session, because there is no person to answer a prompt. Mechanically it is the same session: it starts in a cwd, discovers the same project and user files from there, and applies the same precedence. Nothing below is a new level in the grid; it is how the existing levels behave when nobody can click.

### The one conceptual difference

Interactive permission checks have three outcomes: allow, deny, and ask. Headless has two, because ask has nobody to ask. Every rule you already understand keeps its meaning; only the ask row changes.

| Tool call | Interactive session | Headless session |
|---|---|---|
| Matches an allow rule, no deny | Runs | Runs |
| Matches a deny rule, at any scope | Refused | Refused |
| A `PreToolUse` hook exits 2 | Blocked, hook message shown | Blocked, hook message returned to the model |
| Read-only tool (`Read`, `Glob`, `Grep`) with no rule | Runs | Runs |
| Any other tool with no rule (`Write`, `Edit`, `Bash`, `WebFetch`) | You are asked | Refused. The model sees the refusal, the JSON result lists it under `permission_denials`, and the turn continues |

So a headless session can only do what a rule already permits. This is why an agent that works fine at your keyboard can be read-only when spawned: at the keyboard you were approving each write as it came.

### Where headless grants come from

The same files, same precedence, with one gate. Probed on 2.1.259 in directories the install had never trusted (no entry in `~/.claude.json`), with a UUID canary and a no-rule control:

| Source | Loaded headless in a never-trusted cwd? |
|---|---|
| `~/.claude/settings.json` (user) | Yes |
| `.claude/settings.local.json` allow | Yes |
| `.claude/settings.local.json` deny | Yes |
| `.claude/settings.json` deny | Yes |
| `.claude/settings.json` allow | **No.** Dropped with a stderr warning naming the fix: run interactively there once and accept the trust dialog, or set `hasTrustDialogAccepted` for that path in `~/.claude.json` |
| Hooks in either project file | Yes, they fire |
| `--allowedTools` / `--disallowedTools` | Yes, at command-line scope |
| `--permission-mode acceptEdits` | File edits inside the cwd run with no rule at all |

Once a workspace is trusted, the project `settings.json` allow entries load like everything else. The gate exists because a committed file arrives with a clone and could grant itself anything; trusting the directory once is you vouching for it.

The consequence worth internalizing: an interactive "always allow" click writes a rule into that repository's `settings.local.json`, and headless reads that file. A repository's headless capability is therefore the sum of every approval its owner ever clicked there, plus whatever was written deliberately. Read the file before spawning into a repository, and expect it to hold dozens of one-off `Bash(...)` approvals and no `Edit` rule at all, which yields an agent that can run scripts but cannot save a file.

### Where a grant meant for headless goes

Apply the grid. A grant is enforcement, so it is the "never: enforced" row, and the column is whoever should own the decision.

| Situation | Put the grant in | Why |
|---|---|---|
| This repository's agents should always be able to do X, for everyone who clones it | Project `.claude/settings.json`, then trust the directory once on each machine that spawns there | Committed and reviewable; the trust step is the price of a committed allow |
| Only this machine's spawned sessions in this repository | `.claude/settings.local.json` | Honored headless with no trust step, and never committed |
| The spawner is the authority on what its workers may do | `--allowedTools` / `--disallowedTools` from the spawner | Command-line scope, visible in the process arguments, and a flag deny beats a repository's own allow |
| The spawned session must be able to save files in its cwd and nothing more needs deciding | `--permission-mode acceptEdits` | Grants file edits without enumerating paths; leaves shell and network to the rules |
| Anything that must hold whatever the repository says | A deny rule or a hook at user or managed level | Deny and hooks survive the trust gate and beat every allow |

Never `--permission-mode bypassPermissions` or `--dangerously-skip-permissions` for a spawned session that touches a real repository. It removes the two-outcome table entirely, and the managed setting `disableBypassPermissionsMode` exists to make that impossible fleet-wide.

### Probing rather than reading

A headless permission claim is a guess until a canary shows it. The method: a fresh directory per arm, a UUID that only the tool under test can put on disk or return, one arm with no rule at all as the control, and the verdict read from the file system or the `permission_denials` list, never from the model's prose, because a model refusal and a permission refusal read the same in a final sentence. Pin the CLI version to the result; the version can change between two runs on the same afternoon, and a bump means re-probe.

---
## the-mechanisms

| Mechanism | What it is | Loads | Context cost |
|---|---|---|---|
| `CLAUDE.md` | Instructions you write, read at the start of every session | Session start, in full | Every request, for the whole session |
| `.claude/rules/` | Topic-separated instruction files, optionally scoped to file globs | Session start, or when a matching file is opened | Nothing until it loads, then every request |
| Skill | A markdown file holding knowledge or a workflow, invocable as `/<name>` | Description at session start, body when used | One line per skill at startup, body only on use |
| Subagent | An isolated worker with its own context window that returns a summary | When spawned | Isolated from the main session |
| Hook | A command, HTTP request, prompt, or subagent fired at a lifecycle event | On its event, every time | Zero unless it returns output |
| MCP server | A connection to an external system, exposing tools and data | Tool names at session start, schemas on demand | Low until a tool is used |
| Auto memory | Notes Claude writes to itself and reloads next session | Session start, index only | The first 200 lines or 25KB of the index |
| Plugin | A versioned bundle of the above, installable across repositories | Per its contents | Per its contents |

### The decision procedure

Work down the list. The first question that gets a yes determines the destination.

1. **Must this hold every time, even if the model decides otherwise?**
    Use a hook or a permission rule. "Never edit `.env`" written in `CLAUDE.md` is a request. A `PreToolUse` hook that blocks the edit is enforcement. Instructions shape behavior; they do not guarantee it.

2. **Does it apply only to part of the tree, or only to certain file types?**
    Use a path-scoped rule in `.claude/rules/` with `paths:` frontmatter, or a `CLAUDE.md` inside that directory. Choose the rule when you want all conventions centrally maintained or the same rule applies to scattered paths. Choose the per-directory file when the directory's owners maintain their own conventions alongside their code.

3. **Is it a procedure, checklist, or body of reference material used on some tasks and not others?**
    Make it a skill. Deployment checklists, API style guides, release runbooks, schema documentation. Give it a short description that leads with words a request would actually contain, because descriptions get shortened when many skills are present. Set `disable-model-invocation: true` for anything with side effects, which also drops its context cost to zero until you invoke it.

4. **Does the work read a lot to produce a little?**
    Route it through a subagent. Investigation, log processing, documentation lookups, verification passes. The subagent reads in its own context window and only its summary comes back.

5. **Does answering it require reaching a system outside the repository?**
    Connect that system as an MCP server. Where a good CLI already exists, such as `gh`, `aws`, or `gcloud`, prefer the CLI, since it adds no per-tool listing to context at all.

6. **Is it a short, always-true fact about this repository that every task needs?**
    Put it in `CLAUDE.md`. Build commands, test commands, "use pnpm not npm," where handlers live.

7. **Would Claude work this out for itself given a session or two?**
    Let auto memory hold it. Build quirks, debugging insights, and preferences you correct in chat get saved without you writing anything.

8. **Does a second repository need the same thing?**
    Package it as a plugin. Plugin skills are namespaced, so they never collide with a repository's own.

Two points that save wasted effort. Splitting a `CLAUDE.md` into `@path` imports organizes the content but does not reduce context, because imported files still load at launch; only path-scoped rules and skills defer loading. Hooks also serve as a context tool rather than only an enforcement one: a hook that greps a 10,000 line log for errors and returns the matches turns tens of thousands of tokens into hundreds.

---
## sort-a-block-of-context

Find the row that matches the block you are about to paste into a `CLAUDE.md`.

| What you are pasting | Where it goes | Why |
|---|---|---|
| "Use pnpm, not npm. Run `pnpm test` before committing." | Project `CLAUDE.md` | Short, always true, every task needs it |
| "Never commit directly to main." | A `PreToolUse` hook, plus one line in `CLAUDE.md` | The line states the rule, and the hook is what stops the commit |
| 300 lines of API endpoint documentation | A skill | Reference material needed on some tasks only |
| A 14 step deploy checklist | A skill invoked as `/deploy`, with `disable-model-invocation: true` | It is a procedure with side effects, and you decide when it runs |
| "Go files use tabs, TypeScript uses two spaces" | Two path-scoped rules under `.claude/rules/` | Each applies only when a matching file is open |
| "In `packages/api`, never write raw SQL in route handlers" | `packages/api/CLAUDE.md` | The convention is owned by the area it governs |
| A directory tree or dependency list | Delete it | Claude reads the tree faster than you can keep it current. `/doctor` proposes exactly this trim |
| "Run ESLint after every file edit" | A `PostToolUse` hook | It must happen every time and needs no judgment |
| "Don't read `vendor/` or anything generated" | `permissions.deny` `Read` rules in `.claude/settings.json` | Enforced at the tool layer rather than left to judgment |
| Your database schema and query patterns | A skill, with the connection itself as an MCP server | The MCP server provides access, the skill provides the knowledge to use it well |
| "Our data classification policy applies to all repos" | Managed policy `CLAUDE.md`, with the hard limits as managed `permissions.deny` | It binds every repository, and the parts that can be enforced should be |
| "I prefer verbose commit messages" | `~/.claude/CLAUDE.md` | Personal, cross-project |
| "My staging database is at `https://...`" | `CLAUDE.local.md`, gitignored | Personal and project-specific, must not be committed |
| "Research this before answering, it takes a lot of reading" | A subagent | The reading stays out of the main conversation |
| Anything you have written three times in three repositories | A plugin in an internal marketplace | Copy-paste has no version history and drifts |
| A decision the team reached and the reasoning behind it | A committed file in the repository's knowledge base | A decision stated only in a session reaches nobody else |
| Something Claude worked out that every teammate will hit | Promote it out of auto memory into a rule or a skill, and commit it | Auto memory is machine-local, so it never leaves the machine that learned it |

If a block does not match any row, apply the decision procedure above in order. If it still does not sort, that usually means the block is doing more than one job and should be split.

---
## memory-and-retrieval

Four distinct layers get called "memory," and they answer different questions. Teams that conflate them end up running overlapping systems and trusting none of them.

| Layer | Who writes it | Where it lives | What it answers | When it loads |
|---|---|---|---|---|
| Instructions | You | `CLAUDE.md` and `.claude/rules/` | What are the rules here | Every session, in full |
| Auto memory | Claude, as it works | `~/.claude/projects/<project>/memory/` | What has Claude learned about this repository | The index every session, topic files on demand |
| Session history | A plugin, using hooks | A store the plugin manages | What did we do about this, and when | Only when queried |
| Corpus retrieval | A build step you run | An index file beside the corpus | What does this body of text or code say | Only when queried |

### Auto memory

Auto memory is Claude's own notebook, on by default. It saves build commands, debugging insights, and preferences it picks up from your corrections, then reloads them next session. The directory holds a `MEMORY.md` index plus topic files; the first 200 lines or 25KB of the index loads at session start, and topic files are read on demand.

Scope is what places it in this standard. Auto memory is keyed to the git repository, shared across worktrees, and machine-local, so it does not reach other developers or your other machines. Treat it as an individual productivity layer rather than a team artifact or a record of decisions. Anything the team must agree on belongs in `CLAUDE.md` or a rule, which are versioned and reviewable, and moving it there is an explicit step someone performs rather than something that happens on its own. Disable it per project with `autoMemoryEnabled: false`, or centrally with `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`.

### Session-history memory

Session-history memory is a category of third-party plugin, of which `claude-mem` is one example. It hooks session events, captures observations of what happened, stores them, and exposes search over that store so a later session can ask what a past session did.

It sits at the user level, and it earns its place when continuity is needed across weeks and the reasoning cannot be reconstructed from the code and the commit history. It is not authoritative: it records what happened rather than what was decided, and a decision that exists only in a session log has not been recorded anywhere a teammate can find it.

For an enterprise deployment this is a trust decision before it is a productivity one. Such a plugin reads session content, may run a local service, and typically ships MCP tools. The controls are `allowedMcpServers` and `deniedMcpServers`, marketplace restrictions such as `strictKnownMarketplaces` and `blockedMarketplaces`, and `strictPluginOnlyCustomization`. Decide the policy centrally before individual developers install one.

### Corpus retrieval and knowledge graphs

Corpus retrieval builds an index over a body of text or code that the agent queries as a tool, rather than context that loads into every session. It comes in two forms, and they are worth keeping separate.

**A markdown corpus** is a wiki, an Obsidian vault, or a documentation tree. The index parses headings, frontmatter, tags, and both wikilink and standard markdown link syntax, then addresses **sections** rather than files. A hit returns a heading-bounded passage with a line range, so the agent reads a passage instead of opening a file to find one paragraph. Backlinks make the link graph traversable: "what references this note" becomes a query rather than a search.

**A codebase** has edges of a different kind, since imports and dependencies do the work links do in a wiki. The index carries symbols with line ranges, entry points, and inbound edges, which turns "what is the blast radius of changing this file" into a lookup. For typed languages, check first whether a code intelligence plugin covers the need, since a language server gives symbol navigation and live type errors with no index for anyone to maintain.

An index built this way runs offline and deterministically, with no embedding model involved, which is what makes it cheap enough to rebuild rather than maintain. Treat it as a build output: gitignore it and regenerate it, rather than repairing it or citing it as a source. This is the "LLM wiki" pattern in practice, and its economy comes from the corpus already carrying structure. A corpus authored with headings and links indexes well. A flat dump of logs and transcripts has no structure to exploit, so headings have to be added before an index is worth building.

### When none of this is warranted

Reach for the simplest thing that answers the question.

- The corpus fits in context, or one skill holding the handful of facts people actually ask about covers it.
- Grep and glob already answer the questions you ask in practice. Indexing pays off on repeated questions over a corpus larger than context, not on one-off lookups.
- The corpus changes faster than anyone will rebuild the index, so stale answers would be worse than no index.
- Your organization already runs a code search or RAG service. Expose it as an MCP tool rather than standing up a second index beside it.

---
## the-repository-as-shared-source-of-truth

A team that wants one context, one knowledge base, and one set of skills across a whole delivery does not need a new mechanism.
It needs the project column of the sorting grid to be the only place shared context is allowed to live.
The repository that holds the code also holds the configuration that governs how agents work on it, so a clone is a working station, a pull is the sync, and a pull request is the review gate for behavior as well as for code.

Nothing here is Claude Code specific beyond the paths. The discipline is what makes it hold.

### What the repository carries

| Committed path | What it is | What it gives the team |
|---|---|---|
| `./CLAUDE.md` | Always-loaded project instructions | One set of standing rules, identical for every developer and every agent |
| `./.claude/rules/*.md` | Topic files, optionally scoped with `paths:` | Per-area conventions that load only when a matching file is open |
| `./.claude/skills/<name>/SKILL.md` | Procedures and reference material | Runbooks, checklists, and domain knowledge that any teammate's session can invoke |
| `./.claude/commands/*.md` | Project slash commands | Shared triggers for the procedures above |
| `./.claude/agents/*.md` | Subagents with tool allowlists | The same specialized workers, scoped the same way, for everyone |
| `./.claude/settings.json` | Permissions, hooks, `enabledPlugins`, `extraKnownMarketplaces` | Enforcement and tooling that arrive with the clone rather than by instruction |
| `./.mcp.json` | Project MCP servers | The same external systems, declared once |
| `docs/`, ADRs, `tasks/` | The written knowledge base | Decisions and plans that survive the session that produced them |

The knowledge base is the part teams most often leave out.
Skills and rules tell an agent how to work; a committed `docs/` tree or ADR set records what the team decided and why, which is the thing no agent can re-derive from the code.
Keep it in the same repository as the code it describes unless it genuinely spans repositories, and index it with corpus retrieval only once it outgrows context.

### What must stay out

| Path | Why it is not shared |
|---|---|
| `./.claude/settings.local.json` | Personal permission allowances and machine-specific overrides. Gitignore it |
| `./CLAUDE.local.md` | Personal, project-specific notes such as a staging URL |
| `~/.claude/projects/<project>/memory/` | Auto memory is machine-local and keyed to the repository, so it never reaches a teammate |
| A generated index over the corpus or codebase | A build output. Gitignore it and rebuild it |
| Secrets, tokens, and personal environment URLs | They do not belong in any committed file, agent-facing or not |
| A session-history plugin's store | It records what one developer's sessions did, not what the team decided |

### Where silos form, and the counter-move

Three leaks account for most of the drift. Each has a specific fix.

1. **Knowledge accumulates in auto memory and stops there.**
    Auto memory is per-developer and per-machine by design, so everything Claude learns about the build, the test suite, or a recurring trap stays with the one person whose session learned it.
    The counter-move is an explicit promotion step: at the end of a session, anything durable that was learned gets written into a rule, a skill, or the knowledge base and committed.
    If promotion is not an actual step someone performs, it does not happen, and the team runs on N private notebooks.
2. **Decisions live only in a transcript.**
    A decision argued out in a session exists nowhere a teammate can find it, and a session-history plugin does not fix this because it records what happened rather than what was agreed.
    Write the decision to a committed file at the time it is made.
3. **Assets get copied between repositories.**
    A skill pasted into a second repository has no version history and starts drifting immediately.
    Publish it as a plugin from a marketplace repository instead, and let both repositories install the same version.

### Reviewing the agent assets like code

A change to `CLAUDE.md`, a rule, or a hook changes how every teammate's agent behaves, which makes it a higher-blast-radius diff than most application code.
Treat it accordingly.

- Put `.claude/` under `CODEOWNERS` so the people who maintain the conventions see changes to them.
- Review a rules change for what it will do to sessions that are not the author's. Instructions written for one person's workflow become everyone's default.
- Lint the assets in CI: skill frontmatter validity, the `CLAUDE.md` line cap, no secrets, and no absolute personal paths. `claude plugin eval` covers plugin-packaged skills, and a short script covers the rest.
- Keep one topic per file. A monolithic `CLAUDE.md` is both a context cost and a merge conflict hot spot; separate rule and skill files let several people and several agents edit conventions in parallel without colliding.

### Propagation and staleness

A pull updates the files on disk, not the session already running.
`CLAUDE.md`, settings, and the skill listing are read at session start, so a developer who pulls mid-session keeps working against the old rules until they start a new one.
Say so in the onboarding notes, and restart the session after pulling changes under `.claude/`.
Hook changes are the sharpest case: a removed hook can keep firing from a long-lived process until it is relaunched.

### Scaling past one repository

| Sharing scope | Mechanism | Why |
|---|---|---|
| One project, one team | The repository's own `.claude/` tree | The assets are versioned with the code they govern |
| Several repositories, one org | A plugin published from a marketplace repository, installed via `/plugin marketplace add <owner/repo>` | One version history, namespaced skills, no copies to drift |
| Every repository, non-negotiable | Managed settings and managed policy `CLAUDE.md` | Enforced by the client rather than left to a repository's own configuration |

Committing `extraKnownMarketplaces` and `enabledPlugins` in `./.claude/settings.json` means a clone brings the team's plugin set with it rather than a setup document asking each developer to install it.
Project MCP servers declared in `./.mcp.json` still require each developer to approve them on first use, which is a trust prompt rather than a sync failure.

### The onboarding test

The standard to hold the repository to: a new teammate clones it, starts a session, and gets the same rules, the same skills, the same permissions, and the same knowledge base as everyone else, without being sent a setup document or asking anyone what the conventions are.
Anything that fails that test is either a silo or a missing commit.

---
## the-four-questions

### Sharing context across dev teams without token explosion

The largest saving available is in instructions that sit in `CLAUDE.md` and would do the same work as a rule or a skill. `CLAUDE.md` loads in full on every request for the life of the session. A rule with `paths:` frontmatter loads when Claude opens a matching file. A skill contributes one line at startup and its body only when used. Moving a block from the first category to the third takes it off the bill for every unrelated request. The tradeoff is that a skill loads when Claude matches the request to its description, so the description now does the work the always-on placement used to do, and a vague one will miss.

The practice:

1. Cap each `CLAUDE.md` at 200 lines. Run `/context` to see what loaded and `/doctor` to get proposed trims.
2. Move anything file-specific into `.claude/rules/` with `paths:`. Move anything task-specific into a skill.
3. Delete anything the model can derive from the codebase, which is most directory listings and architecture overviews.
4. To share across repositories, publish a plugin to an internal marketplace. Do not copy files between repositories, because copies drift and have no version history.
5. Know that `@path` imports organize but do not save context. Imported files still load at launch.

### Managing context in large codebases

Scope the session to the code the task touches.

1. Start Claude in the subdirectory you are working in. That determines which `CLAUDE.md` files load and which project settings apply.
2. Put repository-wide rules in the root file and area conventions in per-directory files, maintained by each area's owners.
3. Use `claudeMdExcludes` to skip packages you never work in.
4. Add `Read` deny rules for checked-in generated code and third-party dependencies. Content searches already respect `.gitignore`.
5. Install a code intelligence plugin for typed languages, so symbol lookup replaces file scanning.
6. Put area-specific skills in that area's `.claude/skills/`, and keep descriptions short, because they get shortened when many skills are in scope.
7. Route exploration through a subagent so the file reads stay out of the main conversation.
8. On a long cross-package change, have Claude write the plan to a file in the repository. A file survives compaction; conversation history may not.

### Token cost across a session, checkpointing versus starting over

Every request carries the whole conversation. Prompt caching makes re-reading it cheap, not free, so a one-line question in a session that has been open all day still draws usage for the entire history.

The three tools do different jobs:

| Tool | What it does | Costs | Use when |
|---|---|---|---|
| `/clear` | Starts a new session | Nothing | Switching to unrelated work, which is the common case |
| `/compact` | Replaces history with a summary | A large request, because it reads what it summarizes | You need continuity into the next task |
| `/rewind` or double Escape | Restores conversation and code to a checkpoint | No summarization pass | Claude went down the wrong path and you want the state back |

What survives compaction: the system prompt, `CLAUDE.md`, auto memory, and MCP tools all reload. The skill listing is the exception, and only skills you actually invoked are preserved. Nested `CLAUDE.md` files and path-scoped rules are not re-injected; they reload the next time Claude touches a matching file. Anything stated only in conversation is gone, which is the argument for writing decisions to a file.

Other cost drivers worth knowing: the prompt cache lifetime is one hour on a subscription and five minutes on API or usage credits, so the first message after a long break reprocesses the full context. Idle sessions still spend if a scheduled task fires or an agent teammate is running. Agent teams cost roughly seven times a standard session when teammates run in plan mode.

For budget planning, enterprise deployments average around 13 US dollars per developer per active day and 150 to 250 dollars per developer per month, with 90 percent of users below 30 dollars per active day. Pilot with a small group and use `/usage`, the analytics dashboard, or OpenTelemetry export to establish your own baseline before wider rollout. Sonnet handles most coding work; reserve Opus for architectural and multi-step reasoning tasks, and lower the effort level for simple ones.

### Standing up a knowledge graph over a vault, corpus, or codebase

Decide first whether you need one, using the criteria in the retrieval section. An index earns its keep when the corpus is larger than context and gets asked questions repeatedly.

Then, in order:

1. Check what already exists. If the organization runs a code search or RAG index, expose it through MCP rather than building a second one.
2. For a typed codebase, try a code intelligence plugin first. Symbol navigation with no index to maintain covers many of the cases people reach for a graph to solve.
3. If you are indexing anyway, pick the right parser for the corpus: link and heading structure for a markdown wiki, imports and symbols for a codebase.
4. Store the index beside the corpus, gitignore it, and rebuild it rather than repairing it. It is a build output.
5. Give the agent a skill that says when and how to query the index, so it queries instead of reading files. Query results enter context; the index itself does not.
6. If the corpus is a flat dump with no headings or links, add structure to the corpus first, because an index can only expose structure the corpus already has.

---
## file-path-reference

### Instructions

| Scope | Path |
|---|---|
| Managed policy, macOS | `/Library/Application Support/ClaudeCode/CLAUDE.md` |
| Managed policy, Linux and WSL | `/etc/claude-code/CLAUDE.md` |
| Managed policy, Windows | `C:\Program Files\ClaudeCode\CLAUDE.md` |
| User | `~/.claude/CLAUDE.md`, `~/.claude/rules/*.md` |
| Project | `./CLAUDE.md` or `./.claude/CLAUDE.md`, `./.claude/rules/*.md` |
| Local, gitignored | `./CLAUDE.local.md` |

### Settings

| Scope | Path |
|---|---|
| Managed, macOS | `/Library/Application Support/ClaudeCode/managed-settings.json` |
| Managed, Linux and WSL | `/etc/claude-code/managed-settings.json` |
| Managed, Windows | `C:\Program Files\ClaudeCode\managed-settings.json` |
| User | `~/.claude/settings.json` |
| Project, committed | `./.claude/settings.json` |
| Local, gitignored | `./.claude/settings.local.json` |

### Extensions

| Item | Project path | User path |
|---|---|---|
| Skill | `./.claude/skills/<name>/SKILL.md` | `~/.claude/skills/<name>/SKILL.md` |
| Subagent | `./.claude/agents/<name>.md` | `~/.claude/agents/<name>.md` |
| MCP servers | `./.mcp.json` | `~/.claude.json` |
| Hooks | The `hooks` key in `./.claude/settings.json` | The `hooks` key in `~/.claude/settings.json` |
| Auto memory | Not a project artifact | `~/.claude/projects/<project>/memory/` |

### Commands worth knowing

| Command | Use |
|---|---|
| `/context` | See exactly what loaded into this session and what it costs |
| `/memory` | List and edit instruction files and browse auto memory |
| `/status` | Confirm which managed settings source is active |
| `/doctor` | Get proposed trims for a committed `CLAUDE.md` |
| `/usage` | Token and cost breakdown, with attribution to skills, subagents, and MCP servers |
| `/insights` | A report on how you are working and where the friction is |
| `/init` | Generate a starting `CLAUDE.md` from the codebase |
