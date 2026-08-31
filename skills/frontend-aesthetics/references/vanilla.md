# Taste without dependencies

Field notes from applying this skill to a zero-dependency UI (vanilla HTML/CSS/
JS, no build step, 2026-08-27). The method survives intact; what changes is
that several tells assume a package.json, and a few crafts the catalog never
covers become load-bearing. This file is the correction.

The prior above everything: **reaching for a library is itself a default worth
resisting.** The model adds Tailwind, an icon pack, and a motion library
because designed pages in the training set had them - the same reflex that
produces the beige-and-brass palette. A page that holds up with none of that
is harder to fake and easier to own.

## The stack is the platform

- **Design tokens are CSS custom properties on `:root`.** One block of
  `--bg-*, --text-*, --accent, --border, --font-mono` IS the design system.
  Every hardcoded hex outside that block is a future incoherence.
- **Type: the system stack is a choice, not a fallback.**
  `-apple-system, system-ui, sans-serif` plus one mono stack covers an app UI
  with zero requests. The `default-font` warn targets *reaching for Inter as
  the reflex*; naming the system stack deliberately, for an app (not a brand
  page), passes honestly.
- **Components are template literals plus one `escapeHtml` helper.** No
  framework needed for a panel, a chip, a row list. Every interpolation of
  data you did not write goes through the escaper - this is a security rule
  wearing a style rule's clothes.

## Tells that invert without dependencies

- **`handrolled-icon`**: the warn says "use an icon library" - with no
  dependencies allowed, the correct reading is *consistency is the icon
  system*. One viewBox (24), one stroke width (2), `currentColor`, everywhere.
  Hand-rolled reads as improvised only when the strokes disagree. Survive the
  warn with that one line; fix any icon that breaks the family.
- **`radius-scale`**: square (0) and full-round (50%, 999px) are anchors
  outside the scale. A real app's radius language is `{0, small, large, pill}`
  - one language, four values. The linter now excludes the anchors; the two
  numbers in between are what you commit to.
- **Emoji/em-dash rules run on comments too.** They hide there, and so do
  leftover project names from the repo you ported the pattern from. Lint the
  whole ui directory, not the file you just wrote.

## Continuous state displays (canvas HUDs, meters, live graphs)

The catalog covers pages; agent cockpits also paint *state that changes while
you watch*. Four rules from the field:

- **Decay is a half-life, not a per-frame constant.** `heat *= 0.982` at 60fps
  is "gone in 2 seconds" wearing a disguise; nobody reviewing the diff can
  tell. Write the intent: `factor = 0.5 ** (1 / (halfLifeSeconds * fps))`,
  then say the half-life in the comment. If you inherit a magic constant,
  compute what it means before you keep it.
- **Transient flash vs resting floor.** A retrieval flash that fully fades
  tells the user nothing a minute later. Split the signal: a short-half-life
  pulse for *just happened*, plus a persistent floor proportional to peak
  (`rest = min(cap, peak * 0.45)`) for *happened this session*. The resting
  state is the product; the flash is the feedback.
- **Magnitude wears one hue.** Heat/activity/recency ramps go dark-to-bright
  in a single hue (ideally the app accent), never a rainbow. That rule and its
  validator live in the dataviz skill - state displays are charts and defer
  to it.
- **`prefers-reduced-motion` needs JS for canvas.** The CSS media query cannot
  reach a `requestAnimationFrame` loop. Read it once via
  `matchMedia('(prefers-reduced-motion: reduce)').matches`, then snap
  positions instead of easing and drop decorative pulses. Resting brightness
  must carry the same information the motion carried.

## Motion without a library

- Animate `transform` and `opacity`; the compositor does those for free.
- The one honest exception in a no-build stack: `max-height` for collapse.
  It reflows, but the transform alternative needs measured heights in JS.
  Acceptable on a small subtree at short duration; say so when the linter
  warns.
- Scroll-following views damp, never yank: follow only when the reader is
  already near the bottom; an explicit user action (send) may snap. A stream
  that drags the scroll position is motion nobody asked for.

## Verification is stdlib

Both gates run on a bare mac: `slop_check.py` is Python stdlib and handles
plain `.html/.css/.js` unchanged; the dataviz palette validator runs under
`node` with no packages. There is no dependency-shaped excuse for skipping
either.
