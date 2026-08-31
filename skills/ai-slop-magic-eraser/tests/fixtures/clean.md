# Getting started

Set up the service in three steps. Setup takes about ten minutes and needs a
database URL and an API token.

## Configure

Copy `config.example.toml` to `config.toml` and set two values:

- `database_url` - the Postgres connection string
- `api_token` - read from the secret store, never committed

## Deploy

Run `make deploy`. The command builds a versioned package, uploads it, and
prints the release id.

If the token is missing the deploy fails at the upload step with exit code 3.
There is no rollback command; redeploy the previous release id instead.

```python
# Fixtures and code blocks keep whatever characters they need — including this.
LABEL = "it's important to note that this is a fixture 🚀"
```
