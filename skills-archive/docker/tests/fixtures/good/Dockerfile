# Fixture: the same app, done right. Must lint clean (zero findings).
# Multi-stage, pinned digest, manifest-then-source copy order, non-root, healthcheck.
FROM python:3.13-slim@sha256:1e1b1a1f8f3b9e6b2f9c7a1d0e4c5b6a7f8e9d0c1b2a3f4e5d6c7b8a9f0e1d2c AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim@sha256:1e1b1a1f8f3b9e6b2f9c7a1d0e4c5b6a7f8e9d0c1b2a3f4e5d6c7b8a9f0e1d2c
WORKDIR /app
COPY --from=build /install /usr/local
COPY src/ ./src/

RUN useradd --system --uid 10001 app
USER app

HEALTHCHECK --interval=30s --timeout=3s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"]
CMD ["python", "-m", "src.main"]
