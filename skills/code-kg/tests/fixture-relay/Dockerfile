FROM python:3.12-slim

WORKDIR /srv/relay

COPY pyproject.toml pyproject.toml
COPY src src
COPY migrations migrations
COPY web/public web/public

RUN pip install --no-cache-dir -e .

EXPOSE 8420
CMD ["python3", "-m", "relay.cli", "serve", "--port", "8420"]
