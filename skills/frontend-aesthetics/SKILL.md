---
name: frontend-aesthetics
description: Raises the visual quality of agent-generated UI so it stops reading as AI slop, and audits existing UI against a catalog of tells. Use BEFORE writing the first line of markup for any user-facing surface (landing page, marketing site, dashboard, app screen, docs site) - not after, when the defaults are already baked in. Also use whenever a UI is described as looking generic, templated, "AI-generated", soulless, or "like every other site", when asked to make something look better/more premium/less default, when redesigning or critiquing an existing interface, or when reviewing UI a model produced. Ships a deterministic linter (scripts/slop_check.py) for the countable tells; the judgment calls stay human. Not for chart/data-viz design, and not for layout BUGS (that is debugging, not taste).
license: MIT
---

# frontend-aesthetics

Generated UI is bad in a specific, boring way: the model does not make a
mistake, it makes **the average**. Left to its defaults it emits the statistical
center of every landing page it ever saw, which is why AI sites all look like
each other rather than like anything. Fixing that is bias-correction, not taste.

This skill is a method plus an enforcement mechanism:

1. **Read the room** before designing (below).
2. **Set the dials** explicitly, with reasons.
3. **Design against the defaults**, using `references/tells.md`.
4. **Gate the output** on `scripts/slop_check.py` - mechanical, deterministic,
   no model in the loop. FAIL blocks.
5. **Answer the judgment questions** the linter cannot.

Steps 1-3 are craft. Step 4 is the part most design skills lack: their
"checklist" is run by the same model that wrote the code, which is a model
grading its own homework. A rule a machine can check should be checked by a
machine.

## Step 1 - The design read (one line, before any code)

Declare what you think you are building. Get it wrong out loud and the user can
correct you in one word, before you have written 400 lines in the wrong key.

> Reading this as: **\<page kind>** for **\<audience>**, in a **\<vibe>** language,
> leaning toward **\<system / aesthetic family>**.

The audience picks the aesthetic, not your taste and not mine. A public-sector
service and a fashion label want opposite things and neither is "better design".

Constraints that **override** aesthetics whenever they appear: accessibility
requirements, regulated/public-sector context, existing brand assets, an
established design system in the repo, and anything the user already said they
like. When a constraint and an instinct disagree, the constraint wins.

**Ask at most one clarifying question, and only if the read genuinely forks.**
If you can infer it, infer it. A question dump is its own kind of slop.

## Step 2 - The dials (state the values and the reason)

| Dial | 1 | 10 |
|---|---|---|
| `DESIGN_VARIANCE` | perfect symmetry, equal columns | asymmetric, masonry, deliberate voids |
| `MOTION_INTENSITY` | static, hover states only | scroll-driven choreography |
| `VISUAL_DENSITY` | gallery, huge whitespace | cockpit, packed data, mono numerals |

Infer them from the brief; do not inherit a default. Rough anchors:

- minimal / calm / editorial → `5 / 3 / 3`
- premium consumer / brand → `7 / 6 / 3`
- agency / experimental → `9 / 8 / 3`
- **tooling, dashboards, data-dense** → `4 / 2 / 8`
- trust-first / public-sector / a11y-critical → `3 / 2 / 5`

Coupled rules that follow from the dials:

- `DESIGN_VARIANCE > 4` → centered hero is off the table.
- `MOTION_INTENSITY > 3` → `prefers-reduced-motion` is mandatory, not optional.
- `MOTION_INTENSITY > 4` → the page must actually move. Claiming motion and
  shipping a static page is worse than shipping static.
- `VISUAL_DENSITY > 7` → drop card containers; separate data with 1px rules and
  set numbers in mono with tabular figures.

## Step 3 - Design against the defaults

The full catalog is `references/tells.md` (READ it - do not guess the rules).
**Working with no build step and no dependencies - vanilla HTML/CSS/JS, or a
canvas/state HUD - also read `references/vanilla.md`**: several tells invert
without a package.json, and continuous state displays (decay half-lives,
transient-vs-resting signal, reduced motion on canvas) have their own rules
the catalog does not cover. Adding a library is itself a default to resist.
The short version of what a model reaches for and should not:

- Purple/blue gradient glow. Centered hero on a dark mesh. Three identical
  feature cards. Glassmorphism on everything. Inter + slate-900.
- The beige-and-brass "premium" palette. It is not premium; it is the third one
  this month.
- Decoration that imitates the *signals* of design: `01 / INDEX` eyebrows,
  photo-credit captions on stock images, locale-and-weather strips, `v0.6` hero
  badges, scroll cues, fake terminal windows built out of `<div>`s.
- Em-dashes. Anywhere a user can see them. This is binary because graded
  versions of this rule get ignored.

Rotation matters as much as any single rule: **do not ship the same palette or
display serif twice in a row.** Slop is diagnosed across your outputs, not
within one of them.

## Step 4 - Gate the output (mechanical)

EXECUTE, from the skill directory or with a path to it:

```bash
python3 scripts/slop_check.py <file-or-dir>...     # exit 1 on any FAIL
python3 scripts/slop_check.py --json <path>        # machine-readable
```

Stdlib only, offline, deterministic. **A FAIL is not a suggestion** - fix it or
state plainly why the rule is wrong for this brief. A WARN needs a one-line
reason to survive.

Never hand-wave the gate ("looks clean to me"). If you did not run it, it did
not pass. And a clean lint is a floor, not a ceiling: it proves the countable
tells are gone, nothing more.

## Step 5 - The judgment pass (what the linter cannot see)

Answer these honestly; they are where the real quality lives.

1. **Is there anything actually on the page?** Fake product UI made of `<div>`s,
   a hero with a gradient blob instead of an image, and "minimalism" that is just
   an empty page are all the same failure: decoration standing in for content.
2. **Does the layout vary?** Eight sections, at least four different shapes. No
   third consecutive zigzag. No empty bento cell.
3. **Is every animation motivated?** Say what each one is *for* in one sentence
   (hierarchy, feedback, state change, story). If you cannot, delete it.
4. **Does the copy sound like a person?** Forced metaphors, mock-humble asides,
   cute-but-wrong wordplay: cut them. **Boring copy beats cute copy.** Every
   number is real or labeled mock.
5. **Is it coherent?** One theme, one accent, one icon family, one radius
   language, across the whole page.
6. **Would you defend it?** Not "does it look designed" - does it look like *this
   product* and no other.

## Verifying the skill itself

```bash
python3 -m unittest discover skills/frontend-aesthetics/tests
```

`tests/` proves the linter catches the tells (`fixtures/sloppy.tsx`) **and stays
quiet on clean code** (`fixtures/clean.tsx`). The second is the one that matters:
a linter that flags everything gets muted, and a muted linter protects nothing.
`evals/` holds the trigger cases, including should-NOT-fire ones (charts, layout
bugs, backend work).

## Scope

**Not** chart or data-visualization design - different discipline, different
rules. **Not** layout *bugs* (a nav overlapping on Safari is debugging, not
taste). **Not** a substitute for a real designer on brand-defining work; this
raises the floor, it does not replace the ceiling.

## Provenance

The tell catalog and the dial idea are adapted from
[Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) (MIT, read
2026-07-14), with three deliberate changes, all recorded in
`references/tells.md`: verification is a real script instead of model
self-report; its unsourced prompt-boosting statistics are dropped; and its
hardcoded taste defaults are replaced with brief-inferred dials, because the
audience picks the aesthetic.
