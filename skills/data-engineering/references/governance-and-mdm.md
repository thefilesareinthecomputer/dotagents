# Governance and master data

Catalogs, grants, tags, masking and retention, plus the matching and survivorship work that
turns several source records into one. Grouped together because both answer the same
question: **which version of this is authoritative, and who may see it.**

**Up:** `architecture-decisions.md` set the governance boundary and the isolation stack.
**Down:** the policies here constrain what `transform-dbt.md` can materialize and what
`optimization.md` can push down, because a policy-bearing table optimizes differently.

## Contents

1. [The isolation unit is not where you think](#1-the-isolation-unit-is-not-where-you-think)
2. [Metastore topology and residency](#2-metastore-topology-and-residency)
3. [Grants](#3-grants)
4. [Tag-driven policy and its prerequisites](#4-tag-driven-policy-and-its-prerequisites)
5. [Masking and filtering mechanics](#5-masking-and-filtering-mechanics)
6. [Where enforcement lives](#6-where-enforcement-lives)
7. [Sharing, retention and erasure](#7-sharing-retention-and-erasure)
8. [Schema compatibility as a deploy-order contract](#8-schema-compatibility-as-a-deploy-order-contract)
9. [Master data: matching and survivorship](#9-master-data-matching-and-survivorship)
10. [Golden records and incremental conformance](#10-golden-records-and-incremental-conformance)
11. [Checked and inconclusive](#11-checked-and-inconclusive)

## 1. The isolation unit is not where you think

**The catalog level is the primary unit of isolation, and permission to traverse the
namespace is not permission to read data.** In a three-level namespace the top-level
container is not the isolation boundary; the catalog is. Traversal grants on catalog and
schema convey no data access on their own, and read access is granted separately.

**"The top-level container is our isolation boundary, so one catalog is fine" is a category
error that produces an estate with one blast radius.** It is the single most consequential
misreading of a modern catalog's object model, because it is made once at setup and is
expensive to reverse afterwards.

**Bind a sensitive catalog to named workspaces, because the default is open to every
workspace on the metastore.** Workspace-catalog binding is the mechanism that denies a
privileged user arriving from the wrong workspace. **Its default mode is permissive**, so
this is an opt-in control that must be deliberately applied to the catalogs that need it.

## 2. Metastore topology and residency

**One governance metastore per region per account is an architectural constraint rather than
a preference, and splitting it fragments identity as well as data.** Separate metastores per
environment or per business unit become isolated silos: you lose the single namespace that
makes promotion and read-only sharing simple, **and you fragment users, groups and service
principals into duplicate access-control estates.** The one situation that genuinely
justifies separate metastores is a hard residency or zero-sharing requirement.

**Data residency forces regional metastores, and cross-metastore access is a sharing problem
rather than a query problem.** A single account with region-specific metastores keeps data
physically in-region while preserving one admin, billing and identity layer above them.
Cross-metastore access is not native: it goes through the platform's read-only sharing
protocol, **with the same egress economics as cross-organization sharing.** Price the egress
and mitigate it, by sharing curated aggregates rather than detail and by co-locating the
consuming compute.

**Keep architectural patterns out of the governance structure.** The namespace level carrying
permissions should represent something stable (environment, residency boundary, business
unit); the levels below represent the architecture. Encoding the medallion layer into the
governance boundary makes adding a layer a permissions migration. The full trade is in
`architecture-decisions.md`.

## 3. Grants

**Grant to groups, never to individuals, and source the groups from the enterprise identity
provider.** Where the estate is already on one identity provider, use the platform's native
federation to it rather than a generic provisioning protocol, get nested groups working, and
**do not run both mechanisms at once.** Mixing them is the standard configuration mistake and
it produces membership that disagrees with itself, which is far harder to debug than either
mechanism failing outright.

**Grant at the lowest level that satisfies the need**, remembering that privileges are
additive and inherit downward, so a top-level grant cascades everywhere. **Put sensitive data
in its own namespace** so filters and masks apply at a boundary rather than table by table.

**Object-creating automation and grant-managing automation are usually two different systems,
and the seam is where renames break.** A configuration engine may create catalogs, schemas
and tables while infrastructure-as-code owns the grants on them. **Renaming a schema then
silently orphans its grants**, because one system followed the rename and the other did not.
Know which side owns each object property before any rename, and treat a rename as a
cross-system change rather than a local one.

**Give automation identities no business-data access, and keep CI/CD identities below owner
tier.** Deploy identity and run identity stay separate, per `deployment.md`.

## 4. Tag-driven policy and its prerequisites

**Attribute-based access control shifts the policy surface from the object to the tag.**
Governed tags drive row filters and column masks, so grants stop being per-object and become
per-classification, evaluated against a session-user identity. **This is the only approach
that survives hundreds of tables**, because it covers new tables as they are tagged rather
than requiring a grant per table.

**The operational prerequisites bite, and several fail closed rather than degrading:**

- **A minimum runtime version below which access is refused** rather than degraded. An old
  cluster does not read less; it reads nothing.
- **Single-user compute needs fine-grained access control enabled** and silently proxies
  queries to serverless to evaluate the policy, **so if serverless is disabled those clusters
  are blocked entirely.** That is a surprising coupling between two settings that look
  unrelated.
- **Time travel and cloning fail outright on policy-bearing tables**, which breaks a recovery
  path teams assume they have.
- **A policy-exemption list grants completely unfiltered access to whoever is on it.** It is a
  legitimate mechanism and it is also the thing to audit first when asking who can see
  everything.

**Tag taxonomy is a design artifact.** Keep the sensitive-column registry in version control
with its masking rule, and **add a drift scan that fails the refresh when an unclassified
column appears.** Masking coverage is an enumeration, and enumerations rot as schemas evolve,
so it has to fail closed.

## 5. Masking and filtering mechanics

Four mechanical traps, the first of which is a total security failure with no error message.

**A row filter or mask with a type mismatch between column and function parameter can
silently return everything.** With permissive casting, uncastable values become null, and a
filter written to pass when null then passes every row. **Enable strict-cast mode so the
mismatch raises**, and match parameter types to column types deliberately.

**A masking policy that evaluates as the session user closes the view-as-a-backdoor hole and
breaks the workflows that depended on it.** When downstream views and functions evaluate the
policy against the *querying* user rather than the object owner, a view can no longer expose
filtered base data to a service account. **That is the correct behavior and it is a breaking
change**: every dashboard or script relying on a privileged view suddenly returns filtered
results. Plan the migration and the grace period rather than discovering it on upgrade day.

**Filter and mask functions sit on the hot path of every query, so keep them simple and
deterministic.** The engine will always choose the secure plan over the fast one, so
complexity is paid per query. Prefer simple conditional expressions over lookup tables and
subqueries; minimize distinct masks per table; minimize function arguments, because
referenced columns cannot be optimized away; avoid many conjuncts in one filter; and **avoid
expressions that can throw, because a throwable expression blocks pushdown and an error
message is itself an information leak about pre-filter values.**

**Query-time or dynamic masking is not data protection.** It obscures result sets while files
and backups retain raw values. **Only destructive static masking inside an isolated host makes
a copy safe to move to a lower environment.**

**Row-level security fails open**, which is why it must never be the inter-tenant boundary. A
token minted without a role means no filter, and administrators bypass it when viewing
directly. Use it for intra-tenant scoping only. The full isolation stack is in
`architecture-decisions.md`.

## 6. Where enforcement lives

**Row-level security has to be decided per layer, not once for the estate.** The same
restriction implemented at the raw, conformed, curated and semantic layers has different costs
and different bypass paths.

**The design act is deciding where the authoritative enforcement point is, and documenting
that the other layers deliberately do not enforce it. Implementing the same rule four times is
the failure mode**, because four implementations drift and the weakest one becomes the actual
policy.

**Declare explicitly which layer is not a security boundary.** A SQL or semantic projection
layer no end user authenticates against should be documented as a modelling layer only. One
sentence prevents most future confusion.

**A masked or restricted-visibility source will hand you a short extract rather than an
error**, so "does this account see everything" belongs on the ingestion side too. This is the
same mechanism as the profiling-side visibility check in
`profiling-and-validation.md`, and it is worth stating at both ends because the two teams
involved are usually different people.

## 7. Sharing, retention and erasure

**A masked or filtered table cannot always be shared, and the workaround changes what the
partner gets.** Sharing protocols commonly reject tables carrying row filters or column masks.
The workarounds - share a pre-filtered materialized copy, or exempt the share owner from the
policy - are **both real changes to the security model** and should be recorded as decisions
rather than applied as fixes.

**Treat offboarding, retention and deletion as three distinct cases**: deactivate, churn,
legal erasure. **Collapsing them hides the one case that requires new engineering**, and a
routine aging-out policy is not an answer to a deletion demand it was never designed for.

**Archival has a readability horizon.** Retaining data costs storage and slows queries;
discarding it fails audit. The non-obvious part is the long tail: a multi-decade retention
requirement implies a plan for reading the media and interpreting the format later, which
means periodic refresh and migration rather than write-once. **When retiring a source system,
sunset its data into a vanilla application-independent format before the licence lapses.**

**Version-control and migrate the whole pipeline context as one versioned unit**, and be able
to restore yesterday's complete metadata context. In regulated environments, archive the
pipeline's full logic-and-metadata context alongside the archived data, or a lineage claim
about old data cannot be reconstructed.

## 8. Schema compatibility as a deploy-order contract

**Schema compatibility mode is a cross-team deployment-order contract, not a config value.**

| Mode | Deploy order it mandates |
|---|---|
| BACKWARD (the usual default) | **consumers first** |
| FORWARD | **producers first** |
| FULL | either order |
| transitive variants | same order, validated against all prior versions |

Two hard constraints worth knowing: stream-processing libraries built on the log typically
require the BACKWARD family, and in FORWARD mode a Protobuf schema cannot add new message
types.

**Because it governs deploy ordering across team boundaries, it belongs in an architecture
decision record**, not in a config file nobody reads. Pick wrong and one team's deploy breaks
another team's pipeline, which is the same channel-sequencing failure class as
`deployment.md` §1, arriving through a different door.

**Schema-on-write via a registry is what makes streaming pipelines safe at scale**, and a
metadata catalog plus a schema registry are the required supporting components for treating a
governed log and its table materialization as one product.

## 9. Master data: matching and survivorship

**Deduplication is two separable problems, and the second is where the business lives.**

- **Matching** is technical: deterministic on a shared key, then multi-field fuzzy where no
  universal key exists.
- **Survivorship** is a business-rule set: combining matched records into one image by an
  explicit per-column priority sequence across source systems. **It has to be elicited, not
  inferred.**

Teams routinely staff the first and discover the second at the end. A survivorship rule that
nobody signed off is a rule that will be disputed the first time a number is questioned.

**Buy rather than build for fuzzy matching, survivorship and standardization** where the
matching problem is genuinely fuzzy. That tool category is mature and in wide use. The same
reasoning applies to profiling. **Buy the analysis tools, build the control plane**, because
the screens and the grain encode your business and no vendor can supply them.

**A business key identifies nothing across an estate until it is qualified by its source
system.** Different sources reuse the same codes for different entities, so any conformed
dimension assembled from more than one source must carry the source-system qualifier as part
of its natural key. **Omitting the qualifier produces silent cross-system collisions that look
like duplicate members**, which is the failure most likely to be mistaken for a matching
problem when it is actually a keying problem.

## 10. Golden records and incremental conformance

**A surviving golden record must retain back-reference natural keys to every contributing
source system, or it is unauditable.** Without them, nobody can answer why an attribute has
the value it has, and the first challenge to a number becomes unanswerable.

**Conformance is incremental, and that is what makes master data management shippable.** Two
dimensions are conformed once they share one attribute with the same name and the same
contents. **Add one conformed attribute at a time to each subject area**, and the set of
processes that can participate in cross-process queries grows monotonically. **The big-bang
alternative is what makes these programs fail.**

**Name the small set of standardized dimensions explicitly** - source system, legal entity,
location, organizational unit, revenue stream - and hold both sides to them. Where two regions
or business units each own their own pipelines under shared standards, the enterprise roll-up
works only if both conform to the same curated model, and **naming that set up front achieves
more than any amount of downstream harmonization.**

**A conformed dimension is a deliverable that must be agreed before either side builds.** It
is the one artifact where agreement after the fact costs more than the build itself.

**Data-quality defects are indicators of broken business processes**, and the quality metadata
from the cleansing subsystems is the evidence base for fixing the process upstream. A purely
technical fix routes around the real problem and guarantees recurrence.

## 11. Checked and inconclusive

- **Entity-resolution mechanics** (blocking key design, comparison vectors, probabilistic
  record linkage, threshold and clerical-review-band tuning, evaluation against a labelled set)
  were not researched. The buy verdict stands on the source material; the algorithm detail does
  not appear here.
- **Open-source entity-resolution options**: only two were settled, and both carry licence
  constraints that disqualify the casual assumption of a permissive drop-in. **Zingg core is
  AGPL-3.0** (copyleft, which changes the legal review) and **Senzing's engine is proprietary
  object code, record-metered, with only the SDKs permissive.** Verified 2026-07-29. Splink and
  RecordLinkage were not verified at all.
- **MDM architectural styles** (registry, consolidation, coexistence, centralized) and the
  criteria between them were not researched.
- **Golden-record persistence patterns in a lakehouse** (crosswalk tables, survivorship
  implemented as SQL, versioning of the surviving record, how a match decision is reversed) and
  **stewardship workflow tooling** for adjudicating a low-confidence match are not covered.
- **Hierarchy management as a subsystem** (ragged, variable-depth, versioned hierarchies) is
  not covered here; the modelling side of it belongs to dimensional modelling.
- **Per-platform grant syntax and object models** beyond the principles above are
  version-sensitive; the specific privilege names, inheritance rules and audit-log query recipes
  per platform were not verified.
- **PII discovery-to-classification-to-policy workflow end to end** was not researched. The
  durable part captured here is the drift scan that fails closed on an unclassified column.
- **Retention and erasure mechanics in a lakehouse** - how deletion vectors, time travel and
  file-retention commands interact with a hard-delete obligation, and what the compliant
  sequence actually is - **was not verified, and it is the most consequential unknown here.** Do not
  improvise it; check the platform's current documentation, because the answer changes with
  deletion-vector and retention-command behavior.
