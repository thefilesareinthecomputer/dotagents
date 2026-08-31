# Ingestion Service Spec ✨

Great question — here's the spec!

## Overview

This document describes our robust, comprehensive approach to leveraging a
best-in-class ingestion layer. It's worth noting that the design is somewhat
involved, but it significantly improves throughput.

## So how does it work?

In order to unlock the full potential of the pipeline, the service reads from a
queue, not a database. It's not just faster, but also cheaper. Furthermore, the
retry logic is state-of-the-art.

As mentioned above, the following section covers deployment. That said, it goes
without saying that you should carefully configure the timeouts properly.

The service exposes a `--max-retries` flag and a `--retry-backoff` flag. It also
supports `--retry-jitter`, which defaults to true.

## Key Takeaways

- Setup is easy
- Performance improves by orders of magnitude
- There is no way to disable retries

## Deployment

Deploy with `make deploy`. The rollback command is `make rollback`.
