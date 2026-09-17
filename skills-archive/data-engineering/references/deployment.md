# Deployment

Getting a change into production, in the right order, through every channel it travels
down. **The costliest defect class in data engineering lives here**, and it is not a failed
deploy. It is a successful one that took effect in pieces.

**Up:** `architecture-decisions.md` decided what can be expressed as code at all.
**Down:** `observability.md` catches the partial-promotion states described below, for the
cases where prevention did not hold.

## Contents

1. [Channel sequencing: a merge is not a release](#1-channel-sequencing-a-merge-is-not-a-release)
2. [The layer seams](#2-the-layer-seams)
3. [Config-as-code, and why editing the repository changes nothing](#3-config-as-code-and-why-editing-the-repository-changes-nothing)
4. [Environments](#4-environments)
5. [Identity](#5-identity)
6. [Bundle mechanics](#6-bundle-mechanics)
7. [Infrastructure-as-code mechanics](#7-infrastructure-as-code-mechanics)
8. [The interpolation phase problem](#8-the-interpolation-phase-problem)
9. [Compute for scheduled work](#9-compute-for-scheduled-work)
10. [Cutover and parallel running](#10-cutover-and-parallel-running)
11. [Ownership and sequencing of the work itself](#11-ownership-and-sequencing-of-the-work-itself)
12. [Checked and inconclusive](#12-checked-and-inconclusive)

## 1. Channel sequencing: a merge is not a release

**One change reaches production through several channels that fire on different triggers.**
A single merged pull request can contain all of these, and they activate at different
moments:

| Channel | Activates on | Latency after merge |
|---|---|---|
| Transformation model code | the next scheduled run, sourced from trunk | minutes to a day, no deploy needed |
| Job, pipeline and schedule definitions | a deploy | until someone deploys |
| Runtime configuration rows | a **separate apply step**, per environment | until apply runs *in that environment* |
| Cluster and warehouse settings | restart or next cluster creation | until the next cold start |
| Catalog objects and grants | an infrastructure apply | its own pipeline, its own approval |

**Between the first channel and the last, production runs new code against old
configuration, while every component reports healthy.** That state is not detectable from
any single system's status. It has produced a material misstatement at a period close, which
is why channel sequencing comes before every other deployment concern.

**The rules that follow:**

1. **Enumerate the channels a change travels down, and their triggers, before calling it
   live.** Publish that table, because people get it wrong in **both** directions: assuming
   a model change needs a deploy when it does not, and assuming a config row is live when it
   is not.
2. **Diagnose by tracing what the engine actually reads, never what sits in the
   repository.** This corollary is absolute and it is the fastest route out of most "but I
   changed it" conversations.
3. **A release spanning several systems is not released until every system has been
   promoted.** Where a change touches a bundle-deployed job, a connector configuration and an
   orchestration template, each has its own mechanism and its own approval. **Partial
   promotion produces an environment that is internally inconsistent and passes its own
   tests.**
4. **Validate before promote at every environment hop**, rather than once at the end.

## 2. The layer seams

**The deployment DSLs are layered and the seams are firm.**

| Layer | Owns | Examples |
|---|---|---|
| Infrastructure-as-code | the **platform** | workspace, metastore, catalogs, external locations, network, grants |
| Asset bundle / workload deploy | the **workload** in it | jobs, pipelines, wheels, models, dashboards |
| CI/CD | **promotion** of both, behind gates | authors neither resource type; it invokes the other two |
| Transformation framework | **data** inside the workload | models, snapshots, tests |
| Container | the **code** the workload runs | image, dependencies, entrypoint |

**The two recurring violations are provisioning a metastore from the bundle layer and
deploying a job from raw infrastructure code.** Both work initially and both create an
ownership ambiguity that surfaces at the worst time, when two tools each believe they own
the object.

**CI/CD authors neither resource type.** If your pipeline YAML contains resource
definitions, the seam has been crossed and the gate has become the author.

## 3. Config-as-code, and why editing the repository changes nothing

**When runtime configuration lives in a table, the repository is a seed and editing it
changes nothing until a loader runs.** This is the most expensive misunderstanding in a
config-driven platform: an engineer edits the versioned configuration, has it reviewed,
merges it, deploys with no errors, and that night's run behaves exactly as before.

Three consequences, each counter-intuitive:

- **An apply step that merges rather than replaces means deleting a row from source control
  does not stop it running.** The live row persists because nothing told the loader it was
  gone. **Disabling is an explicit flag change that must itself be applied.** Any
  config-as-code loader needs a documented answer to "how do I remove something", and
  merge-only semantics make that answer surprising.
- **An apply step that runs per environment leaves a deployed seed inert until it has run
  there.** Confirming the row is live in the *target* environment's configuration table is a
  required step, not a paranoid one.
- **A destructive-change guard should be a first-class, overridable configuration block.** A
  replace-strategy loader that can delete rows needs a maximum-rows-deleted bound, a
  maximum-percentage bound, and an explicit allow-destructive switch. Making the override
  explicit and reviewable turns "the deploy wiped the config" into a pull request someone had
  to approve.

**Shard large configuration tables into multiple files so a diff stays reviewable.**
Reviewability is the entire justification for config-as-code; **a config file too large to
review has discarded the benefit and kept the ceremony.**

## 4. Environments

**Environments are selected by deployment target and configuration, never by branch.** A
single trunk with per-target configuration means a lower environment's test result is
meaningful for production, because the code and the artifact version are identical and only
configuration differs. **Environment branches guarantee the opposite**: they diverge, and the
divergence is discovered at promotion, which is the most expensive moment to discover it.

**CI builds and publishes a versioned artifact; a separate release deploys it, and that is
where approvals live.** Lower environments and production run the same published package, and
neither is developed in directly. **Conflating build and deploy removes the only natural
place to put a human gate.**

**Separate state per environment beats named workspaces for production isolation**, because
workspaces share a backend and it is easy to apply to the wrong one.

**Cloning production data down to a lower environment moves production data into a weaker
control regime.** The policy needs a named per-source allow-list and a masking or subsetting
rule for anything personal, decided before the first clone. **The clone must be deep rather
than shallow**, or the lower environment reads production's files and breaks the moment a
retention boundary moves.

## 5. Identity

**Keep the deploy identity separate from the run identity.** The identity that creates jobs
and uploads files needs broad workspace permissions; the identity that executes the code
needs only the data access the job requires. **Collapsing them means every scheduled job runs
with deployment-level privilege.**

**A project developed against a personal token breaks at the first scheduled run under a
service principal**, because the object grants were only ever tested against a human's
entitlements. Give scheduled runs a service identity from the start rather than at
promotion.

**Give automation identities no business-data access, and keep CI/CD identities below owner
tier.**

**Prefer federated short-lived credentials over stored secrets in CI.** The runner presents
an identity token, the cloud exchanges it for temporary credentials, and nothing long-lived
is stored or rotated. On some workflow platforms this requires an explicit token-write
permission that is easy to omit. **Expect the migration to break token caching before it
breaks anything else**: when a CLI moves its cached interactive credentials from a plain file
into an OS keychain, headless runners that scraped that file break, while machine-to-machine
flows are unaffected, which is itself the argument for using them.

**Committed configuration files are not a secret store**, in either the infrastructure or the
workload layer. Reference a secret scope or inject from the environment. Note also that
**infrastructure state files contain plaintext secrets**, which makes backend encryption and
state exclusion from version control mandatory rather than advisable.

## 6. Bundle mechanics

**Development-versus-production mode is the multi-environment mechanism, and it is behavioral
rather than cosmetic.** Development mode prefixes resource names per user, pauses schedules
and triggers, sets pipelines to development mode, and isolates each developer so many
engineers can deploy the same bundle into one workspace without collision. Production mode
removes prefixing, activates schedules, enforces a service-principal run-as identity, and
applies stricter path validation.

**The classic first-production-deploy failure is a current-user-interpolated path plus a
missing service principal.** It works for every developer and fails once, in production, on
the first deploy.

**Target-override merge semantics are the sharpest edge: mappings deep-merge but sequences
(task lists, cluster definitions, library lists) do not merge intuitively, and the behavior
has varied across CLI releases.** The reliable practice is to **run the validate command and
read the resolved output rather than reason about a merge rule.** Corollary: **pin the CLI
version**, because the bundle schema shifts across releases and an unpinned runner eventually
breaks on a day nobody changed anything.

**Brownfield adoption has a specific two-step path: generate configuration from the existing
manually created resource, then bind it**, so it comes under management without being
recreated. That is what makes legacy-heavy estates adoptable incrementally. **Hard rule: a
single resource must never be split between managed and manual state.**

**A bundle-managed resource edited by hand reverts on the next deploy.** This is correct
behavior, because configuration is the source of truth, and it is a reliable source of
surprise. **Say it out loud when handing a platform to an operations team**, because they will
otherwise fix an incident by hand and watch the fix disappear.

**Build a versioned package and run an entry point rather than executing notebooks in
production.** The artifact-build plus wheel-task pattern is what makes "no notebooks in
production" concrete rather than aspirational.

## 7. Infrastructure-as-code mechanics

**The plan is a change-control artifact, not a preview.** That is the actual argument for
infrastructure-as-code in risk-averse and regulated estates: an auditable, reviewable,
approvable diff. Presenting it as a convenience undersells it to exactly the audience that
most wants it.

**Modern infrastructure-as-code moved state surgery out of the imperative CLI into
declarative config blocks** - rename and restructure, import, drop-from-state-without-destroying,
and post-apply assertions - **so refactors appear in the reviewed plan instead of happening
out-of-band.** Prefer the declarative form for exactly that reason.

**Keyed iteration beats indexed iteration for resource addressing**, because removing a middle
element from an indexed collection re-indexes everything downstream and produces
destroy-and-recreate churn on unrelated resources. This is a one-line choice with a
multi-hour consequence.

**Every back-room change goes through scripting and testing** - schema deploys, added
columns, index changes, aggregate redesign, database parameters, backup and restore - against
a test environment configured identically to production.

**Version-control and migrate the whole pipeline context as one versioned unit**, and be able
to restore yesterday's complete metadata context. In regulated environments, archive the
pipeline's full logic-and-metadata context alongside the archived data, or **a lineage claim
about old data cannot be reconstructed.**

## 8. The interpolation phase problem

**"My variable did not expand" is almost always a phase mismatch rather than a syntax
error.** Every tool in the chain substitutes at a different moment:

- infrastructure plan versus apply
- bundle validate versus deploy
- workflow expression evaluation before the step versus at runtime
- template compile time versus step runtime
- template render before the SQL executes
- image build versus container run

**The canonical trap worth memorizing: a CI platform with three distinct syntaxes for
compile-time parameters, runtime variables and runtime expressions.** They look similar,
they are not interchangeable, and the failure is a silently empty string rather than an
error.

The diagnostic that works regardless of tool: **render the resolved output and read it.** Do
not reason about what should have substituted.

## 9. Compute for scheduled work

**A per-run cluster defined inside the deployment artifact is preferable to a long-lived
shared cluster for scheduled work.** It is versioned with the job, it cannot accumulate state
or library conflicts from other users' work, and it terminates when the job does, which is
also the highest-value cost guardrail per `cost.md`.

**A transformation framework cannot always share a general-purpose cluster.** Where a SQL
transformation tool conflicts with other code on a shared all-purpose cluster, the correct
target is a SQL warehouse. Where a model is written in Python rather than SQL, it needs a
different compute type **in the same project**, so a project standardized on a warehouse has
to make an explicit exception for it rather than discovering the conflict at run time.

**Compute policy design is a cost and governance control**, and it belongs in the
infrastructure layer rather than in each job. It caps node size, node count and instance type
before a cluster can exist, which is a prevention rather than a report.

## 10. Cutover and parallel running

**A parallel replacement estate that writes to a sandbox target cannot collide with
production, and that same property lets the two diverge unnoticed.** Deploying a rewritten
pipeline alongside the incumbent, writing to a separate schema, is the safe way to build
toward cutover. The cost is that **nothing forces the two to agree**, so logic drift
accumulates silently.

Two consequences follow, and the first is frequently treated as optional when it is not:

1. **A scheduled equivalence comparison is mandatory.** The two-way per-table diff is in
   `profiling-and-validation.md`.
2. **At cutover, the ownership of every shared-but-ambiguous object has to be resolved
   deliberately**: schedules, permissions, downstream registrations. Anything neither estate
   clearly owns is what breaks the morning after.

**Expand-contract is the safe shape for a schema migration**, and the reason it matters here
is the channel-sequencing law: adding the new column, backfilling, moving readers, then
removing the old column are four releases, not one, and compressing them re-creates exactly
the partial-state problem in §1.

## 11. Ownership and sequencing of the work itself

**The ownership boundary that works: the platform team owns ingestion into the raw layer;
domain teams own everything from the conformed layer to presentation.** One shared platform
team setting standards, security, patterns and CI/CD, with domain teams building inside those
guardrails. This avoids both the duplicated-platform failure, where every domain reinvents
ingestion, and the bottleneck failure, where one team builds every model. **"One platform
team" does not mean one team per environment.**

**Do not adopt a domain-oriented mesh without the conditions for it.** Argue against it when
there is no platform team providing self-service infrastructure, when domains have no
engineering capacity to own products, or when the organization is small enough that a central
team is genuinely faster. **The dominant failure mode is renaming without changing
anything**: calling the existing central warehouse a mesh, with federated governance and
product ownership never actually established.

**The delivery sequence for a data product**: define, govern, connect and discover, land,
model, validate, enable consumption, deploy and operate. **Two orderings matter most and are
violated most often.** *Govern before connect*: decide catalog and schema structure,
personas, permissions and sensitivity classification **before data lands**, because
retrofitting access control over landed sensitive data is a migration rather than a change.
*Validate before promote*, at every hop.

**An onboarding intake form should end in a readiness score, not a plan.** Score business
value, urgency, data readiness (access established, subject-matter experts identified,
business logic documented, validation baseline confirmed) and delivery complexity separately,
each with written anchors per level, and let the scores decide sequencing. **Readiness is a
distinct axis from value**, so a high-value request with no access and no expert correctly
sorts below a lesser request that can actually be built, and the next step for an unready
item is a spike rather than a delivery estimate.

**Batch remains the correct default and streaming is the exception**, so a streaming-first
mandate is an architecture error dressed as ambition. The decision turns on whether
sub-minute latency changes an operational action: it does for fraud interception, live
telemetry and real-time personalization; it does not for financial close, executive reporting
or model training. Complex multi-table joins, historical restatement and point-in-time
auditability are all materially easier in batch. **"AI readiness" is a demand for clean,
governed, high-context data, not for low latency; streaming dirty data produces wrong answers
sooner.**

**Concentrated tribal knowledge is a structural risk with observable artifacts**: ad-hoc
notebooks outside the deployment artifact, operations performed only through a vendor UI with
no scripted equivalent, manual point-and-click fixes that follow no written procedure, and at
least one component with no owner and nothing in source control that produces it. Each is
individually excusable and collectively a single point of failure. **Name the unowned
components explicitly in the architecture document**, because an unowned component nobody has
written down does not get fixed.

**Two documentation disciplines that keep a platform's docs usable.** *Own the map and link
to the mechanisms*: one document owns the end-to-end flow and the load-bearing facts, and
every mechanism lives in the document that owns it, because **restating a mechanism in two
places guarantees the copies diverge and the stale one is what a newcomer finds.** And *tag
every factual claim with its evidence class*: settled by captured code or notes; inferable
but must be verified against the running system; not present in the sources examined, so
verify rather than assert absence; and affirmative evidence of absence. The justification is
asymmetric cost, since **one unlabelled wrong claim in front of a stakeholder costs more than
three missing details.**

## 12. Checked and inconclusive

- **Terraform module layout for a lakehouse estate** (state bootstrapping, multi-workspace and
  multi-region metastore topology, module boundaries, provider authentication patterns) was
  not researched. The durable seam is in §2; the estate layout is not established here.
- **Which catalog objects belong in the infrastructure layer versus the workload layer** has a
  clear principle (platform versus workload) and no verified per-platform boundary list.
- **Bundle CLI version-specific merge behavior** is stated as varying across releases, which is
  itself the guidance. No specific version's behavior is asserted, and the validate-and-read
  practice is the mitigation precisely because the rule is not stable.
- **Pull-request-time data diffing and regression comparison tooling** was not researched, and
  no tool is recommended.
- **A formal data-pipeline test pyramid** (unit, contract, integration, regression, and where
  each runs in CI) is partially covered by the four instruments in
  `profiling-and-validation.md`; the CI placement of each stage is not established.
