# Landing the work on the right branch

The repo's workflow decides this, not a default baked into the skill.
Read what this repo's `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md` and this workspace's memory actually say about branching; never carry another repo's routine in, and never assume a convention that is not written down.

| Shape | What wrap-up does | Ends on |
|---|---|---|
| Single branch | commit, push | that branch |
| Paired stable branch (a `develop` that a `main` follows) | push the working branch, then advance the stable one **by refspec, never by checkout** | the working branch |
| Feature branch | commit and push the feature branch only | the feature branch |

## The paired shape, and why the refspec form matters

```bash
git push origin <working>:<stable>
git fetch origin <stable>:<stable>
```

Checking out the stable branch across a commit that deletes tracked files restores them and then re-deletes them, and newly ignored files never appear in `git status` while it happens.
The refspec form never touches the working tree.

Both commands refuse a non-fast-forward rather than forcing one, and that refusal is the safety property.
A non-fast-forward rejection means the stable branch has its own commits, which is divergence and a stop-and-ask.
Any other rejection is a policy problem to surface verbatim.

## Feature branches: what happens after the push

When in doubt, do less.

- **The repo's working agreement explicitly says the agent opens PRs at phase end.**
  After the push, open the PR into the integration branch that agreement names, with a descriptive body built from the actual diff - summary, changes by area, verification evidence - honoring whatever gate the agreement sets, for example the user's in-session sign-off that the phase is complete.
  The user still merges; never merge.
- **No such agreement on record - the default.**
  Wrap-up gets the work safely onto the remote and stops.
  Opening a PR is then a separate decision with review attached.
  Say that it stopped there and why.

## Confirming the end state

```bash
git status -sb        # clean, and on the branch work belongs on
git branch -vv        # every tracked branch in sync
```

Confirm it rather than assuming it.
