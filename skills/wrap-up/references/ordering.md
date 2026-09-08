# Why the chain runs in this order

Each step's output is the next step's input, so the sequence is not arbitrary.
Numbers are the step numbers used by SKILL.md's headings, so they start at zero.

0. **Fetch before anything.**
   Inbound commits from another machine can change what is true.
   Reconciling the session against stale state produces memory entries and doc corrections that are wrong on arrival.
   This is the one place the obvious order - work first, git last - is wrong.

1. **Security review once, after the commit and before the push.**
   It reviews everything since the last push, so it sees the commit and what reflect and notes wrote, and it never has to run again because nothing in the chain writes after it.
   Run early, it fires on every later edit and turns the chain into a loop; run at the gate, a Critical finding is amended into the one commit that exists and the push waits.
   The push is the exposure boundary, so the gate sits there.

2. **Inbox before reflect.**
   Unprocessed peer mail carries decisions, findings and corrections from other agents.
   Reflecting before draining it produces memory entries that a message in the inbox already contradicts.

3. **Reflect before notes.**
   Reflect corrects stale claims wherever they live.
   Notes then documents the session against a record that is already accurate.
   Reversed, notes writes up claims reflect is about to overturn.

4. **Notes before commit.**
   The docs sweep changes files.
   Committing first means committing twice or amending.

5. **Commit before push, with a second fetch between.**
   The fetch from step 0 is stale by now; another machine may have pushed during the session.

6. **Branch parity last**, because it advances a branch to a commit that must already exist on the remote.

## Why step 0 is safe to run before any decision

The four `status`, `symbolic-ref` and `branch` reads are pure reads.
`git fetch` writes only remote-tracking refs under the git directory, so it cannot touch the working tree, local branches or commits.
Nothing that can modify the tree happens until after both approval gates.

`origin/HEAD` is often unset, in which case `symbolic-ref` fails and `git branch -vv` is the real evidence of branch shape.

## What only the security review catches

Two classes reach nothing else in the chain.

**Secrets and personal or station-specific constants** that a later step is about to publish.
Cheap to remove now, permanent once pushed.

**Changes to the agent tooling itself** - hooks, sync scripts, subagent definitions, settings files - where the blast radius is every future session on every machine rather than this repo.
That is why the review is not optional when the session touched shared tooling: it is the gate standing between a mistake and a fleet-wide one.

## Why the parallel split is where it is

The security review is a subagent spawned after the commit; the push blocks on its verdict.
That is the only synchronization point the ordering actually requires.
