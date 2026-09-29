# Taste without dependencies

Read this reference when building without dependencies or a build step: plain HTML, CSS, and JavaScript, or a canvas or state display. Several tells assume a `package.json`, and a no-build UI depends on a few crafts the tell catalog does not cover. [foundations.md](foundations.md) owns tokens, the dials, and static moves, and [interaction.md](interaction.md) owns motion, timing, and reduced motion.

The prior above everything: **reaching for a library is itself a default worth resisting.** Tailwind, an icon pack, and a motion library tend to arrive before the page has shown it needs them. A page that holds up with none of that is harder to fake and easier to own.

## The stack is the platform

- **Design tokens are CSS custom properties on `:root`.** One block of custom properties, with the roles and scales from [foundations.md](foundations.md), is the design system. Every hardcoded hex outside that block is a future incoherence.
- **Type: the system stack is a deliberate choice.** `-apple-system, system-ui, sans-serif` plus one mono stack covers an app UI with zero requests. The `default-font` warning targets reaching for Inter by reflex; a system stack named deliberately for an app, rather than a brand page, passes honestly.
- **Components are small functions that build DOM nodes.** No framework is needed for a panel, a chip, or a row list. Build with `createElement`, insert data with `textContent`, and swap a region's contents with `replaceChildren`, so text you did not write never reaches the HTML parser. One escaping helper around markup strings does not secure every interpolation context: attribute values, URLs, CSS, and script each need their own handling, and a URL assigned to `href` needs validation even through DOM APIs. Security implementation follows the project's engineering practice.

## Tells that invert without dependencies

- **`handrolled-icon`**: the warning says "use an icon library". With no dependencies allowed, consistency is the icon system: every icon uses one viewBox (24), one stroke width (2), and `currentColor`. Hand-rolled icons read as improvised only when the strokes disagree. Answer the warning with that one-line reason, and fix any icon that breaks the family.
- **`radius-scale`**: square (0) and full-round (50%, 999px) are anchors outside the scale. A real app's radius language is `{0, small, large, pill}`, one language with four values. The linter excludes the anchors, so the two values in between are the scale you commit to.
- **The `emoji` and `em-dash` rules run on comments too.** Both hide there, and so do leftover project names from the repo you ported a pattern from. Lint the whole UI directory as well as the file you just wrote.

## Continuous state displays (canvas HUDs, meters, live graphs)

The tell catalog covers pages; a dashboard or HUD also paints *state that changes while you watch*. Four rules apply:

- **Decay is a half-life over elapsed time.** A per-frame factor such as `heat *= 0.982` hides its intent and ties speed to the frame rate: it halves in 0.64 seconds at 60 Hz, in 0.32 seconds at 120 Hz, and more slowly when frames drop. Write `heat *= 0.5 ** (deltaSeconds / halfLifeSeconds)` with the half-life named in seconds, and convert an inherited per-frame constant to the half-life it implies at its tuned frame rate before keeping it.
- **Transient flash vs resting floor.** A retrieval flash that fully fades tells the user nothing a minute later. Split the signal: a short-half-life pulse for *just happened*, plus a persistent floor proportional to peak (`rest = Math.min(cap, peak * 0.45)`) for *happened this session*. The resting state is the product; the flash is the feedback.
- **A meter, heat ramp, or live graph is a chart**, so its color ramp, scale, and axes defer to the dataviz skill.
- **`prefers-reduced-motion` needs JS for canvas.** The CSS media query cannot reach a `requestAnimationFrame` loop. Keep one `matchMedia('(prefers-reduced-motion: reduce)')` query, check `matches` before starting motion, and listen for its `change` event so a preference switched mid-session settles the display at once. Under reduce, snap positions instead of easing and drop decorative pulses; resting brightness must carry the same information the motion carried. [interaction.md](interaction.md#reduced-motion) has the full runnable pattern.

## Motion without a library

- Prefer `transform` and `opacity`, then measure rendering cost in a performance trace; [interaction.md](interaction.md#feedback-and-responsiveness) covers what those properties still cost.
- The one honest exception in a no-build stack is `max-height` for a collapse. It reflows, but the transform alternative needs heights measured in JavaScript. It is acceptable on a small subtree at a short duration; give that reason when `animate-layout-prop` warns.
- Scroll-following views damp and never yank: follow only when the reader is already near the bottom, and let an explicit user action such as sending a message snap to the end. A stream that drags the scroll position is motion nobody asked for.

## Verification is stdlib

`slop_check.py` and `check_contrast.py` are Python standard library scripts, and the linter reads plain `.html`, `.css`, and `.js` files unchanged. A no-dependency stack has no reason to skip either.
