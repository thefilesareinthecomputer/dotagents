---
name: docker
description: Scaffolds, operates, reviews and hardens containerized projects - from a cold start or inside an existing repo. Use when containerizing an app, when authoring or editing any Dockerfile/Containerfile/compose file, when inheriting an unfamiliar repo that has one, when a build is slow, an image is fat, or the layer cache never hits, when a container runs as root or leaks secrets into layers, when a container will not start or dies mysteriously (137/OOM, 126, 127), when debugging a container, reclaiming disk, or pushing to a registry, and when reviewing container config before it ships. Also use before granting a container ANY host privilege (Docker socket, privileged, host network, bind-mounting /), which warrants a hard stop. Ships scripts/docker_check.py and drives hadolint and trivy.
license: MIT
---

# docker

An agent writing a container gets the same three things wrong every time: it
runs as **root**, it bakes **secrets into layers**, and it copies the whole tree
before installing dependencies so the **cache never hits**. All three are
mechanical, all three are checkable, none of them require judgment.

## First: which situation is this?

**Existing setup → orient before touching anything.** Read
`references/runbook.md` § *Inheriting an existing setup*. A working container you
find ugly beats a beautiful one that no longer boots, and the odd choices usually
encode a constraint you cannot see yet. Run `docker compose config` (the
*resolved* file - rarely what the YAML appears to say), then the linter, then
**triage**: host-escape grants first, baked secrets second (and **rotate** them -
deleting the line does not un-publish the layer), root user third, size and cache
last. Do not silently "clean up" a two-year-old Dockerfile as a side effect of an
unrelated task.

**Cold start → scaffold.** Read `references/scaffold.md`: multi-stage templates
for Python/Node/Go, the `.dockerignore` that comes first, dev-vs-prod compose,
and how to pick a base image. They already pass the linter.

Then, either way:

1. **Write / change it** against the rules below.
2. **Operate it** - `references/runbook.md`: build flags, debugging a running
   container, decoding exit codes (137 is OOM and looks like nothing at all), fat
   images, dead caches, reclaiming disk without deleting your dev database,
   pushing to a registry.
3. **Gate it** on `scripts/docker_check.py` (deterministic; FAIL blocks).
4. **Then run the real tools** - `hadolint`, `trivy`, `dockle`. This skill drives
   them; it deliberately does not reimplement them.

Two rules of thumb the templates encode, worth stating plainly because an agent
gets both wrong by default: **build-time and run-time are different machines**
(everything the compiler needed, the server does not), and **dev and prod are
different compose files** (dev mounts your source and reloads; prod bakes it in
and drops privileges) - not one file with a flag.

## Read this before granting any privilege

**Mounting `/var/run/docker.sock` into a container is root on the host.** Not
"a risk" - an equivalence. Anything with the socket can launch a privileged
container that mounts `/`, and container isolation gives you exactly nothing,
because escaping it is the *point* of the mount.

This matters right now because **Docker's own MCP catalog ships a server that
does this** - an MCP tool taking arbitrary `docker` argv with the socket mounted
in (verified 2026-07-14 in `docker/mcp-registry`). Their Toolkit docs advertise
"no host filesystem access by default" and say nothing about it. If an agent has
that tool, then anything that prompt-injects the agent has root on the machine.

If you want an agent to drive Docker: **use plain `docker` commands through the
normal permission prompt.** Visible, auditable, revocable per command. Do not
install a socket-mounted MCP server to save yourself typing.

The same reasoning applies to `privileged: true`, `network_mode: host`,
`CAP_SYS_ADMIN`, and bind-mounting `/`. The linter FAILs on each. Overriding one
is a decision to state out loud, with a reason, not a default to accept.

## The rules that matter

**Secrets.** A layer is permanent. `ENV API_KEY=...`, `ARG DB_PASSWORD=...`, or
`COPY .env` puts the value in the image *forever* - `docker history` reads it
back even if a later layer deletes the file. Use BuildKit
`RUN --mount=type=secret`, or inject at runtime. A secret that ever hit a layer
is burned: rotate it, do not patch it.

**Identity.** Every container gets a non-root `USER`. Without it, a container
escape is a host root escape. `useradd --system --uid 10001 app` then `USER app`.

**Reproducibility.** `FROM python:latest` means today's build is not tomorrow's.
Pin a tag, ideally a digest (`@sha256:...`). An unpinned base is a supply-chain
dependency you did not choose.

**Supply chain.** `ADD https://...` fetches whatever the server serves at build
time. `curl | sh` executes whatever it returns. Pin a version, verify a checksum,
or vendor the file.

**Layer order is a performance API.** Docker caches per instruction and
invalidates everything downstream of a change. So: copy the *manifest*
(`requirements.txt`, `package.json`), install deps, *then* copy source. `COPY . .`
before the install means every one-character source edit reinstalls the world.

**Size.** Multi-stage: build in a fat stage, copy only the artifact into a slim
one. Compilers, headers, and package caches do not belong in a shipped image.
`pip install --no-cache-dir`, `apt-get install --no-install-recommends`, and one
`RUN` chain per logical step (`apt-get update && install && rm -rf
/var/lib/apt/lists/*` - split across RUNs, the cleanup does not shrink anything,
because the earlier layer still holds the files).

**Operability.** A `HEALTHCHECK`, or the orchestrator cannot tell *running* from
*wedged*. A `.dockerignore`, or `.git`, `.env`, and `node_modules` get shipped to
the daemon and can land in the image.

## Gate the output

EXECUTE:

```bash
python3 scripts/docker_check.py <dir-or-file>...   # exit 1 on any FAIL
python3 scripts/docker_check.py --json <path>
```

Stdlib, offline, no daemon contact - it reads text. It covers what the standard
tools miss: **compose-level host-escape grants** (hadolint does not read compose
at all), secrets baked into layers, and cache-destroying layer order.

Then run the mature tools, which are healthy, actively maintained, and better at
their own jobs than anything this skill could reimplement:

```bash
hadolint Dockerfile          # Dockerfile lint (shellcheck for RUN lines)
trivy image <tag>            # CVEs, misconfig, secrets, SBOM
trivy fs .                   # same, without building
dockle <tag>                 # image-level security lint (CIS)
```

If a tool is not installed, say so and offer to install it - do not silently skip
it and call the container reviewed.

## The judgment pass

The linter cannot see these:

1. **Is the base image right?** `slim` vs `alpine` (musl breaks manylinux wheels
   and can wreck Python performance) vs `distroless` (no shell - great for prod,
   miserable to debug).
2. **Is the layer split honest?** Multi-stage is not automatically fewer bytes if
   you copy the whole build stage across.
3. **Does the runtime need what the build needed?** Compilers, `git`, and dev
   headers almost never belong in the final image.
4. **Is the healthcheck real?** One that always returns 0 is worse than none - it
   tells the orchestrator a wedged container is fine.
5. **What happens on OOM or a bad deploy?** Restart policy, resource limits, and
   whether a crash loop is visible or silent.

## Verify

```bash
python3 -m unittest discover skills/docker/tests
```

Fixtures: `tests/fixtures/bad/` (hazardous - must FAIL) and
`tests/fixtures/good/` (correct - must be **silent**). The quiet test is the one
that matters; a linter that fires on a correct Dockerfile gets muted, and a muted
linter protects nothing.

## Ecosystem note (verified 2026-07-14)

There is **no Docker agent skill** in any major collection - not
`anthropics/skills`, not `obra/superpowers`, not `addyosmani/agent-skills`. The
plugin layer is thin and stale (`docker/claude-plugins` has no LICENSE file).
Docker Inc owns the MCP layer (Toolkit/Catalog is GA), with the socket caveat
above. The durable, low-risk tooling is the three CLIs - which is why this skill
drives them instead of competing with them.
