---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - data-engineering
  - ingestion
  - cdc
---

# Ingestion Patterns

How data enters the [[DATA-BRONZE-LAYER|bronze layer]]. Three families cover
most sources; picking between them is mostly about how the source exposes
change.

## Batch pulls

Scheduled full or incremental extracts. The load-bearing detail is the
**watermark**: a cursor column (updated_at, an id, a log sequence number)
that says where the last pull stopped. Watermarks must be stored with the
load, monotonic, and trusted - a source that back-dates updates under a
stale watermark is how rows silently go missing while every run reports
green.

## Change data capture (CDC)

Log-based capture (Debezium-style, or a managed connector) streams inserts,
updates, and deletes as events. Bronze lands them append-only with
operation markers; [[DATA-SILVER-LAYER|silver]] collapses them to current
state via MERGE on the business key. CDC buys freshness and delete
visibility at the cost of connector operations and ordering care.

## File drops and streams

Landing zones (auto-loader on cloud storage, OneLake shortcuts on
[[DATA-LAKEHOUSE-PLATFORMS|Fabric]]) and event streams (Kafka, Event Hubs).
The pattern is the same: discover new input incrementally, record what was
consumed, write [[DATA-DELTA-LAKE-FORMAT|Delta]] append batches.

## Invariants regardless of pattern

- Idempotent loads: re-running yesterday must not double yesterday.
- Late data is normal; watermarks and merge keys handle it, hope does not.
- Landing metadata (source, batch id, arrival time) rides every row -
  [[DATA-QUALITY-EXPECTATIONS|quality checks]] and replays depend on it.
