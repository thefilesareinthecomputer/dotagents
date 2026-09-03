---
type: reference
title: Business Requirements
description: What this project is accountable for delivering, and the constraints it delivers under.
tags:
  - requirements
  - brd
skills:
  - <a skill this project requires>
status: draft
date-created: YYYY-MM-DD
last-modified: YYYY-MM-DD
---

# Business Requirements

The top of the ladder. Every story in [[user-stories]] rolls up to something stated here, and anything in flight that does not is either scope creep or a requirement nobody wrote down.

## Project

Who this is for, what they asked for, and the dates the work is bounded by.

## Current state

What exists today, stated plainly enough that someone joining in month three can tell what was already there from what this project built.

## Desired state

What is true when this is done. Written so that it can be checked rather than argued about.

## Scope boundaries

What is in, and what is explicitly out. The out list is the one that earns its keep.

## Constraints

Budget, access, compliance, platform, skills. Each one with who owns it. The skills the project requires are also listed in this note's `skills:` frontmatter, which is what a knowledge base diffs against to find the gaps.

## Decisions

Settled decisions that constrain the work, newest first. Anything still open belongs in [[notes-questions]], not here.

- YYYY-MM-DD - <the decision> - <why>

## Related

- [[user-stories]] - the work this document is the aggregate of
- [[notes-questions]] - the open questions against these requirements
