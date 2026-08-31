# Scaffolding a containerized project

Templates that already pass `scripts/docker_check.py`. Copy, then adapt - do not
retype from memory, that is how the root user and the cache-busting COPY come
back.

## Contents

- [Decide first](#decide-first)
- [Python (uv / pip)](#python-uv--pip)
- [Node (pnpm / npm)](#node-pnpm--npm)
- [Go (static, distroless)](#go-static-distroless)
- [.dockerignore](#dockerignore)
- [Compose: dev vs prod](#compose-dev-vs-prod)
- [Multi-service: frontend, API, database](#multi-service-frontend-api-database)
- [Choosing a base image](#choosing-a-base-image)

## Decide first

Three questions, answered out loud, before any file exists:

1. **Build-time vs run-time.** What does compiling need that running does not?
   Everything in that gap belongs in a discarded stage.
2. **Dev loop vs shipped image.** Dev wants your source bind-mounted and a
   reloader. Prod wants the source baked in and no reloader. These are two
   different compose files, not one file with a flag.
3. **What must never enter the image.** Secrets, `.git`, test fixtures, the
   `.venv`. That answer is the `.dockerignore`, and writing it first is cheaper
   than discovering a leaked `.env` in a published layer.

## Python (uv / pip)

```dockerfile
# Pin a digest: a tag can be re-pointed under you.
FROM python:3.13-slim@sha256:<digest> AS build
WORKDIR /app

# Manifest first, install second, source last - this is the whole cache story.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim@sha256:<digest>
WORKDIR /app
COPY --from=build /install /usr/local
COPY src/ ./src/

RUN useradd --system --uid 10001 app
USER app

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
HEALTHCHECK --interval=30s --timeout=3s \
  CMD ["python", "-c", "import urllib.request;urllib.request.urlopen('http://localhost:8000/healthz')"]
CMD ["python", "-m", "src.main"]
```

With `uv` (faster, and the lockfile is the manifest):

```dockerfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache
```

A build-time secret, done correctly - mounted, never layered:

```dockerfile
RUN --mount=type=secret,id=pip_token \
    PIP_INDEX_URL="https://$(cat /run/secrets/pip_token)@pypi.internal/simple" \
    pip install --no-cache-dir -r requirements.txt
# docker build --secret id=pip_token,src=./token.txt .
```

## Node (pnpm / npm)

```dockerfile
FROM node:22-slim@sha256:<digest> AS build
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY . .
RUN pnpm build && pnpm prune --prod

FROM node:22-slim@sha256:<digest>
WORKDIR /app
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
USER node                      # the node image already ships a non-root user
HEALTHCHECK --interval=30s CMD ["node", "-e", "fetch('http://localhost:3000/healthz').then(r=>process.exit(r.ok?0:1))"]
CMD ["node", "dist/main.js"]
```

## Go (static, distroless)

The best case: nothing in the final image but the binary.

```dockerfile
FROM golang:1.24@sha256:<digest> AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/app ./cmd/app

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/app /app
USER nonroot:nonroot
ENTRYPOINT ["/app"]
```

No shell means no `docker exec` debugging. That is the trade: hostile to
attackers, hostile to you. Use the `:debug` variant when you need a shell.

## .dockerignore

Write this **first**. Everything not excluded is uploaded to the daemon and can
land in a layer.

```
.git
.env
.env.*
*.pem
*.key
__pycache__/
*.pyc
.venv/
node_modules/
dist/
.pytest_cache/
.mypy_cache/
**/*.md
Dockerfile*
docker-compose*
```

## Compose: dev vs prod

Dev - source mounted, reloader on, ports exposed to you only:

```yaml
# compose.dev.yml
services:
  api:
    build:
      context: .
      target: build          # stop at the fat stage; it has the dev tooling
    command: uvicorn src.main:app --reload --host 0.0.0.0
    volumes:
      - ./src:/app/src:ro    # read-only: the container should not edit your source
    env_file: .env           # gitignored, never COPYed
    ports:
      - "127.0.0.1:8000:8000"   # bind to loopback, not 0.0.0.0
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set it in .env}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 5

volumes:
  pgdata:
```

Prod - nothing mounted, nothing reloaded, privileges dropped:

```yaml
# compose.prod.yml
services:
  api:
    image: registry.example.com/api:${TAG:?}
    restart: unless-stopped
    read_only: true
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true
    tmpfs:
      - /tmp
    deploy:
      resources:
        limits:
          memory: 512M
```

Note what is **absent** from both: no `privileged`, no `network_mode: host`, no
`/var/run/docker.sock`, no `- /:/host`. If you are reaching for one of those,
stop and read the privilege section of SKILL.md.

## Multi-service: frontend, API, database

One container or several is a deployment decision, not a different job. Every rule
above still applies per service. What changes is the wiring, and three decisions
carry it.

**Does the frontend ship as files or as a process?** An SPA that compiles to static
assets has no production container at all - the proxy serves the build output, and a
service whose only job is running `serve` is a container you invented. Server-side
rendering (Next, Nuxt, SvelteKit in SSR mode) genuinely needs a Node process, so it
gets one. Decide this before writing any compose file, because it determines whether
"web" is a service or a build stage.

**Publish from the proxy and nothing else.** In a single-service compose you expose
the app port because there is no other way in. The moment a proxy exists, it owns the
only published port and every other service is reachable by service name over the
compose network. This is the concrete security gain of splitting, and it is the part
most often skipped.

**Put the database on an internal network.** `internal: true` gives it no route off
the host, in either direction. A compromised dependency in the API cannot use the
database as an egress path.

For a static frontend the final stage is the proxy, which is what keeps it off the
service list:

```dockerfile
# web/Dockerfile
FROM node:22-alpine@sha256:<digest> AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build                   # emits /app/dist

FROM caddy:2-alpine@sha256:<digest>
COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
USER 1000:1000                      # the caddy image runs as root otherwise
HEALTHCHECK --interval=30s CMD ["wget", "-qO-", "http://localhost:8080/"]
```

A non-root proxy cannot bind 80 or 443, so it listens on 8080 and compose maps the
privileged port to it. That is the trade for dropping root, and it is why TLS
usually terminates at a load balancer in front rather than here. Terminating it in
this container means granting `CAP_NET_BIND_SERVICE` back, which is a decision to
make deliberately rather than by copying a template.

Dev - real dev servers with hot reload, proxied so that paths match production:

```yaml
# compose.dev.yml
services:
  proxy:
    image: caddy:2-alpine
    volumes:
      - ./Caddyfile.dev:/etc/caddy/Caddyfile:ro
    ports:
      - "127.0.0.1:8080:8080"     # the only published port, loopback only
    depends_on: [web, api]

  web:
    build:
      context: ./web
      target: build               # the fat stage; it has the dev tooling
    command: npm run dev -- --host 0.0.0.0
    volumes:
      - ./web/src:/app/src:ro

  api:
    build:
      context: ./api
      target: build
    command: uvicorn src.main:app --reload --host 0.0.0.0
    volumes:
      - ./api/src:/app/src:ro
    env_file: .env
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set it in .env}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 5

volumes:
  pgdata:
```

The dev proxy routes to the dev server rather than to built files, so hot reload
survives the hop:

```
# Caddyfile.dev
:8080
handle /api/* {
	reverse_proxy api:8000
}
handle {
	reverse_proxy web:5173
}
```

Prod - the frontend is baked into the proxy image, the database is unreachable from
outside, and every service drops privileges:

```yaml
# compose.prod.yml
services:
  proxy:
    image: registry.example.com/web:${TAG:?}
    restart: unless-stopped
    read_only: true
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true
    tmpfs:
      - /tmp
    ports:
      - "80:8080"                # privileged port outside, unprivileged inside
    networks: [edge]
    depends_on: [api]

  api:
    image: registry.example.com/api:${TAG:?}
    restart: unless-stopped
    read_only: true
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true
    tmpfs:
      - /tmp
    deploy:
      resources:
        limits:
          memory: 512M
    networks: [edge, internal]
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:17-alpine
    restart: unless-stopped
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 5
    networks: [internal]         # no ports, no route out

networks:
  edge:
  internal:
    internal: true

volumes:
  pgdata:
```

Name every service's networks once you declare any, because a service with no
`networks:` key silently joins the default network and quietly undoes the isolation
you just wrote.

**When one container is still right.** A single process with no separate frontend
build and no database of its own does not need any of this. Splitting for its own
sake buys a network to debug and nothing else.

## Choosing a base image

| Base | Use when | Cost |
|---|---|---|
| `-slim` | default for Python/Node | glibc, sane debugging, ~80MB |
| `alpine` | you need the smallest and control the deps | **musl** - breaks manylinux wheels, and Python can be measurably slower |
| `distroless` | production services, no shell wanted | no shell: no `exec` debugging (use `:debug` tag) |
| `scratch` | static Go/Rust binary | nothing at all, including CA certs and timezones |
| full (`python:3.13`) | build stage only | do not ship it |

Default to `-slim`. Reach for `alpine` only with a reason, and never reflexively
for Python - the musl wheel problem is real and costs more time than the
megabytes are worth.
