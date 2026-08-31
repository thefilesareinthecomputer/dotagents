# Operating containers

The day-two half: build, inspect, debug, clean up, ship. Diagnostics first -
most container problems are misdiagnosed, and the fix for the wrong diagnosis is
a rebuild that changes nothing.

## Contents

- [Inheriting an existing setup](#inheriting-an-existing-setup)
- [Build](#build)
- [Debug a running container](#debug-a-running-container)
- [Debug a container that will not start](#debug-a-container-that-will-not-start)
- [Why is my image so big](#why-is-my-image-so-big)
- [Why does my cache never hit](#why-does-my-cache-never-hit)
- [Reclaim disk](#reclaim-disk)
- [Ship it](#ship-it)

## Inheriting an existing setup

**Most container work is brownfield.** Do not open with a rewrite: a working
container you find ugly is worth more than a beautiful one that no longer boots,
and the existing choices usually encode a constraint you cannot see yet.

Orient first:

```bash
# What exists, and what does it actually build?
find . -maxdepth 2 \( -name 'Dockerfile*' -o -name '*compose*.y*ml' \) -not -path './node_modules/*'
docker compose config              # the RESOLVED compose: env substituted, files merged, overrides applied
docker images | head               # what has been built here before
docker ps -a                       # what is running or died

# What is already wrong?
python3 scripts/docker_check.py .  # host-escape grants, baked secrets, cache order
hadolint Dockerfile                # if installed
trivy fs .                         # CVEs + secrets, without building
```

`docker compose config` is the one people skip. It shows the *merged, resolved*
file - every `.env` substitution, every override layered in - which is frequently
not what the YAML appears to say.

Then **triage, do not sweep**:

1. **Host-escape grants first** (`docker-socket-mount`, `privileged`,
   `root-fs-mount`). These are live exposure and each is a one-line diff. If one
   is load-bearing (a CI runner genuinely needs the socket), say so out loud and
   scope it, rather than deleting it and breaking their pipeline.
2. **Baked secrets.** Any hit means the credential is already in the image's
   history and in every registry that pulled it. **Rotate it** - removing the line
   does not un-publish the layer.
3. **`runs-as-root`.** Usually a small diff (`useradd` + `USER`), but check
   whether anything writes to a path only root can write. That is why it was
   omitted.
4. **Cache order and image size.** Real wins, zero risk, but they are performance
   work - do them after the security items, not instead of them.

A `FAIL` in a repo that has been shipping for two years is still a FAIL. It is
not, however, automatically *your* emergency: report it, size the fix, and let
the owner decide. What you must not do is silently "clean it up" as a side effect
of an unrelated task.

## Build

```bash
docker build -t app:dev .
docker build --progress=plain --no-cache -t app:dev .   # see every step; suspect a stale cache
docker build --secret id=token,src=./token.txt .        # never ARG a secret
docker build --platform linux/amd64 -t app:dev .        # on Apple silicon, building for x86 prod
```

Cross-arch matters more than people expect: an image built on an M-series Mac is
`arm64` and will not run on an `amd64` host. If prod says `exec format error`,
that is this.

## Debug a running container

```bash
docker ps                                  # what is actually up
docker logs -f --tail 100 <name>           # first stop, always
docker exec -it <name> sh                  # get inside (no shell on distroless)
docker inspect <name>                      # env, mounts, network, restart policy
docker stats <name>                        # live CPU/mem - is it OOM-throttling?
docker top <name>                          # what is it running as? (should not be root)
docker port <name>                         # is the port even mapped?
```

**Distroless has no shell.** Attach a debug sidecar into the same namespaces
instead of rebuilding the image:

```bash
docker run -it --rm --pid=container:<name> --network=container:<name> \
  nicolaka/netshoot sh
```

## Debug a container that will not start

The exit code tells you most of it:

| Exit | Means | Look at |
|---|---|---|
| 0 | the process finished | your `CMD` is not a long-running server |
| 1 | app error | `docker logs` |
| 125 | the *daemon* refused | your `docker run` flags are wrong |
| 126 | command not executable | missing `+x`, or a shell script with CRLF line endings |
| 127 | command not found | wrong path, or a shell-less base image |
| 137 | SIGKILL - **usually OOM** | `docker stats`, raise the memory limit |
| 139 | segfault | often an arch mismatch (arm64 image on amd64) |
| 143 | SIGTERM | it was asked to stop; fine |

```bash
docker logs <name>                         # works on stopped containers too
docker run --rm -it --entrypoint sh app:dev   # bypass the entrypoint and look around
docker inspect <name> --format '{{.State.ExitCode}} {{.State.OOMKilled}}'
```

`OOMKilled: true` is the single most misread container failure - it presents as
a mysterious restart loop with no error in the logs, because there is no error:
the kernel killed it.

## Why is my image so big

```bash
docker images app:dev                      # the number
docker history app:dev --no-trunc          # which LAYER is the number
```

`docker history` is the answer 90% of the time, and it also reveals **every
secret ever baked into a layer** - which is why an `ENV API_KEY=...` is not
fixable by deleting it in a later layer. The value is still there. Rotate it.

Usual culprits, in order: the build stage got copied wholesale instead of just
the artifact; the package cache was never cleaned (`rm -rf /var/lib/apt/lists/*`
must be in the **same** `RUN` as the `apt-get install`, or the earlier layer
still holds the files); dev dependencies shipped to prod; `.dockerignore` is
missing so `.git` came along.

## Why does my cache never hit

Docker invalidates the changed instruction and **everything after it**. So one
misplaced `COPY . .` above the dependency install means every source edit
reinstalls the world.

```dockerfile
COPY requirements.txt .          # changes rarely  -> layer is cached
RUN pip install -r requirements.txt
COPY src/ ./src/                 # changes constantly -> only this layer rebuilds
```

`scripts/docker_check.py` flags the inverted order as `cache-busting-copy`.

Other cache killers: a `COPY . .` with no `.dockerignore` (any file touched, even
a log, busts it), and `ARG`s declared before the stable layers (an `ARG` change
invalidates everything below it).

## Reclaim disk

```bash
docker system df                     # look BEFORE you prune
docker image prune                   # dangling images only - safe
docker builder prune                 # the build cache, usually the real hog
docker system prune -a --volumes     # DESTRUCTIVE: also deletes named volumes = your dev databases
```

The last one is the command people paste from a blog post and then lose their
Postgres data to. `--volumes` deletes named volumes, not just anonymous ones.
Run `docker system df` first, and never suggest `-a --volumes` to someone whose
data you have not asked about.

## Ship it

```bash
docker tag app:dev registry.example.com/app:1.4.0     # never :latest as the only tag
docker push registry.example.com/app:1.4.0
docker buildx build --platform linux/amd64,linux/arm64 --push -t registry/app:1.4.0 .
```

Before pushing anything public: `trivy image <tag>` for CVEs and secrets, and
`docker history --no-trunc <tag>` to confirm nothing sensitive is in a layer.
A push is not reversible - deleting a tag does not un-publish the content that
anyone already pulled, and layer digests persist.
