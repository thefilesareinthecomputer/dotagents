# The tells

The catalog of things that make generated UI read as generated. Adapted from
`Leonxlnx/taste-skill` (MIT, read 2026-07-14), reorganized around one question
the original never asks: **can a machine check this?**

That split is the whole design. Anything countable is enforced by
`scripts/slop_check.py` and is not a matter of opinion. Anything judgment-based
is listed here as a prompt for a human (or a reviewing agent) and is honestly
labeled as such. The original blurs the two and calls the result a
"Pre-Flight Check" - but its checks run inside the same model that wrote the
code, which is the model marking its own homework.

## Contents

- [Why slop happens](#why-slop-happens)
- [Tier 1 - countable (enforced by the linter)](#tier-1---countable-enforced-by-the-linter)
- [Tier 2 - judgment (human/agent review)](#tier-2---judgment-humanagent-review)
- [Rules deliberately NOT adopted](#rules-deliberately-not-adopted)

## Why slop happens

Slop is not a mistake. It is the model's **statistical center of mass** - the
average of every landing page in the training set. Left alone, a model does not
produce a bad design; it produces *the most likely design*, which is the same
design every other model produces. That is why the tells recur build to build
and repo to repo.

Three consequences worth internalizing:

1. **Slop is diagnosed across outputs, not within one.** A beige-and-brass page
   is fine once. It is a tell because it is the *third* one this month. Hence the
   rotation rules: do not ship the same palette or display serif twice running.
2. **Soft rules fail on models.** "Use em-dashes sparingly" gets ignored;
   "zero em-dashes, the output fails otherwise" gets obeyed. Binary rules survive
   contact with a language model. Graded ones do not.
3. **Most tells are performative craft** - decoration that mimics the
   *signifiers* of design without the substance. Photo-credit captions on stock
   images. `01 / INDEX` eyebrows. Fake terminal windows built from `<div>`s.
   Locale-and-weather strips. The model emits these because designed pages have
   them, not because the content needs them.

## Tier 1 - countable (enforced by the linter)

Run `python3 scripts/slop_check.py <path>`. FAIL blocks; WARN needs a reason.

| Rule | Severity | The check |
|---|---|---|
| `em-dash` | FAIL | Any `—` or `–` in UI text. The most reliable single tell. |
| `banned-palette` | FAIL | The 13 beige/brass/oxblood/espresso hexes of the "premium consumer" default. |
| `emoji` | FAIL | Emoji codepoints in UI text. Reads as chat, not product. |
| `h-screen` | FAIL | Breaks under mobile browser chrome; `min-h-[100dvh]` is correct. |
| `scroll-listener` | FAIL | Raw `addEventListener('scroll')`. Janks the main thread. |
| `placeholder-comment` | FAIL | `// rest of code`, `// TODO`, bare `...`. The model stopped early. |
| `lorem-ipsum` | FAIL | Fake copy hides real layout problems. |
| `stock-name` | FAIL | John Doe, Acme, SmartFlow. |
| `scroll-cue` | FAIL | "Scroll to explore". They are looking at the hero; they know. |
| `eyebrow-budget` | FAIL | Eyebrows > `ceil(sections / 3)`. The fix is deletion, not rewording. |
| `pure-black-white` | WARN | `#000`/`#fff` kill depth. |
| `default-font` | WARN | Inter/Roboto/Helvetica as the default reach. |
| `banned-font` | WARN | Fraunces / Instrument Serif / Playfair - the LLM display-serif reflex. |
| `lucide-icons` | WARN | The default icon library. Fine if already a dependency. |
| `handrolled-icon` | WARN | Inline `<svg><path>` icons read as improvised. In a zero-dependency stack this inverts: a CONSISTENT hand-rolled family (one viewBox, one stroke, currentColor) is the icon system - see `vanilla.md`. |
| `gradient-text` | WARN | `bg-clip-text` on a heading. The 2023 AI-landing signature. |
| `custom-cursor` | WARN | Accessibility- and performance-hostile. |
| `animate-layout-prop` | WARN | Animating top/left/width/height forces reflow. |
| `flex-percent-math` | WARN | `w-[calc(33%-1rem)]` is what Grid is for. |
| `middot-spam` | WARN | More than one `·` per line. It is a separator, not a texture. |
| `radius-scale` | WARN | More than two distinct in-between corner radii. Square (0) and full-round (50%, 999px) are anchors outside the scale and do not count; `{0, small, large, pill}` is one language. |
| `filler-verb` | WARN | Elevate, Seamless, Unleash, Next-Gen, Revolutionize. |
| `fake-precision` | WARN | `99.99% uptime`, `10x faster`. Real numbers or no numbers. |
| `performative-craft` | WARN | "Quietly trusted by", "Field notes". |
| `section-number-eyebrow` | WARN | `01 / INDEX`. Decoration pretending to be structure. |
| `hero-version-label` | WARN | `v0.6` / `BETA` as hero garnish. |
| `placeholder-as-label` | WARN | Placeholder as the only label; fails a11y the moment they type. |

## Tier 2 - judgment (human/agent review)

The linter cannot see these. Do not pretend otherwise.

**Layout**
- Three identical feature cards in a row. The default composition; almost never the right one.
- Centered hero, when the brief is anything but a manifesto or launch page.
- The same layout family twice. Eight sections should use at least four different shapes.
- More than two consecutive image+text zigzags.
- A bento grid with an empty cell. N items means N cells; an empty one means you planned wrong.
- Hero that does not fit the viewport: headline over 2 lines, subtext over ~20 words, CTA below the fold.
- Long lists (>5 items) dumped into a `<ul>` instead of a component that fits.

**Substance**
- **Fake product UI built from `<div>`s** - fake dashboards, fake terminals, fake task lists. Their nominated #1 tell, and correctly so: it is the purest form of decoration-instead-of-content.
- A pure-text page called "minimalism". Minimalism is a choice about what to remove; an empty page is unfinished work.
- Copy that sounds like a model trying to sound thoughtful: forced metaphors, mock-humble asides, cute-but-wrong wordplay. **Boring copy beats cute copy.**
- Motion with no reason. If you cannot say in one sentence what an animation is *for* (hierarchy, feedback, state change, story), delete it.
- Claimed motion that does not move. A page that says "cinematic" and sits still is broken.

**Coherence**
- One theme per page. Sections do not invert.
- One accent color, used everywhere. A warm-grey site does not grow a blue CTA in section 7.
- One icon family, one stroke width.
- One corner-radius language.

## Rules deliberately NOT adopted

Recorded so the omissions are choices, not oversights.

- **The "$200 tip / take a deep breath" prompt-boosting numbers.** The source repo
  cites `+45% quality`, `34%→80% accuracy`, `+115% combined` to a "December 2025
  controlled study", EmotionPrompt, and LazyBench - with no authors, no DOIs, no
  URLs. Unverifiable. Repeating unsourced numbers to sound rigorous is itself a
  tell.
- **Their exact dial defaults (`8 / 6 / 4`).** The dials are a good idea and are
  kept; those specific defaults encode the author's taste, not yours. This skill
  infers the dials from the brief and the audience instead of shipping a hardcoded
  preference. The audience picks the aesthetic.
- **The serif blanket-discouragement.** "Creative brief means serif" is a real
  reflex worth naming, but the source overcorrects into near-prohibition. Named
  reflex fonts stay flagged; serif as a category does not.
- **The two internal contradictions.** The source's `stitch-skill` *recommends*
  Fraunces and Instrument Serif, which `taste-skill` bans by name; its `soft-skill`
  *mandates* eyebrow tags, which `taste-skill` caps at one per three sections. The
  skills were never reconciled because they ship separately. Resolved here in
  favor of the stricter rule in both cases, and noted rather than silently picked.
