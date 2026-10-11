---
date-created: 2026-08-27
last-modified: 2026-08-27
status: canonical
tags:
  - data-engineering
  - lakehouse
  - databricks
  - fabric
---

# Lakehouse Platforms: Databricks and Microsoft Fabric

Two managed homes for the same
[[DATA-MEDALLION-ARCHITECTURE-OVERVIEW|medallion architecture]]. Both sit on
open table formats ([[DATA-DELTA-LAKE-FORMAT|Delta Lake]] first), both pair
compute with a governance layer, and both expose broad public REST APIs
(surveyed in the research tier: the Databricks and Fabric API notes).

## Databricks in one paragraph

Compute-centric: clusters and serverless SQL warehouses over your cloud
storage, Unity Catalog as the [[DATA-GOVERNANCE-CATALOGS|governance]] spine,
Lakeflow (jobs + declarative pipelines) for orchestration and
[[DATA-QUALITY-EXPECTATIONS|expectations]], strong ML/serving story. You
bring cloud accounts and think in workspaces, clusters, and catalogs.

## Fabric in one paragraph

SaaS-centric: everything is an item (lakehouse, warehouse, notebook,
pipeline, semantic model) inside workspaces, storage unifies under OneLake
with shortcuts into external data, capacity units meter all compute, and
Power BI is native at the [[DATA-GOLD-LAYER|gold]] end. You bring a tenant
and think in items, capacities, and domains.

## Choosing (the short version)

- Deep engineering and ML platform, multi-cloud posture: Databricks leans
  ahead.
- Microsoft-first estate, BI-heavy consumption, one SaaS bill: Fabric
  leans ahead.
- Either way the medallion pattern, [[DATA-INGESTION-PATTERNS|ingestion]]
  discipline, and [[DATA-BRONZE-LAYER|bronze]]/[[DATA-SILVER-LAYER|silver]]
  contracts transfer unchanged - the architecture is the portable part.
