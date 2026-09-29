# Interaction and motion

Use these patterns when a surface involves controls, motion, or asynchronous states. They make an interface acknowledge input on the next frame, deliver one committed moment when the brief asks for immersion, and give every user the same information and control whatever their motion preference, pointer, or browser. Every duration and curve here is a starting convention; measure the result on the project's target devices and adjust with a reason.

**Contents**

- [What motion is for](#what-motion-is-for)
- [Choreography checklist](#choreography-checklist)
- [Scroll-scrubbed scenes](#scroll-scrubbed-scenes)
- [Timing and easing](#timing-and-easing)
- [Feedback and responsiveness](#feedback-and-responsiveness)
- [Reduced motion](#reduced-motion)
- [Orchestrated entrance](#orchestrated-entrance)
- [Hover and press](#hover-and-press)
- [View transitions](#view-transitions)
- [Scroll-driven enhancement](#scroll-driven-enhancement)
- [Asynchronous states](#asynchronous-states)
- [Scroll and control](#scroll-and-control)
- [What a screenshot cannot show](#what-a-screenshot-cannot-show)

## What motion is for

State what an animation communicates before choosing its duration: an input registered, a state changed, an element came from somewhere or went somewhere, two views are related, or the page's one committed moment is happening. An animation with no answer to that question gets removed. The `MOTION_INTENSITY` dial in [foundations](foundations.md#the-three-dials) sets how much motion a surface carries, and no value on it requires motion that communicates nothing.

An expressive or immersive brief commits its boldness to one primary element or moment and delivers it in the rendered result: a focal image that carries its position into the detail view, or a single orchestrated entrance. Supporting elements stay disciplined so the emphasis stays legible. A page with no memorable element is a craft defect of the same rank as decoration on every section. Neither defect outranks task completion or access, so a moment that delays the task or hides information from reduced-motion users is the first thing cut. For immersion, keep the focal element recognizable across navigation and state changes so orientation persists; a static focal composition is also a deliberate direction. A constrained product screen, such as an operational queue, carries its direction through hierarchy and local feedback without spectacle.

## Choreography checklist

Before coding, storyboard observable start, intermediate, and finished states. For every motion, specify its purpose, changing property, trigger, duration or scroll range, easing, stop condition, and reduced-motion still. Name the shared progress source, phase boundaries, and behavior on reversal, interruption, anchor entry, and resize. Keep controls available throughout.

Build the complete static page first. Enhance behind capability and preference checks; cancel pending frames when reduced motion changes. Use motion to explain causality, such as a press initiating a scan. Keep headings, frames, axes, labels, and captions still while the subject moves. Reserve stable boxes for changing readouts and use tabular numerals. A loop needs a narrative or state purpose and appropriate controls; repeated decoration has no automatic place in the choreography.

## Scroll-scrubbed scenes

Choreograph the scene from one clamped progress source mapped into named phases, with holds at both ends long enough to inspect the starting state and finished result. Keep the frame still while the subject moves, and choose each phase's easing to match the action it communicates. A scroll-scrubbed pin is one way to carry a peak; a static full-bleed composition, a timed entrance, or an interactive control are equally valid when the subject calls for them.

Smooth displayed progress by elapsed time, `p += (target - p) * (1 - Math.exp(-dt / 90))`, with milliseconds and a 90ms starting convention. Snap on large jumps and endpoints; stop requesting frames when settled.

This standalone example reveals an illustrative sample profile with a cursor and clip rectangle driven by the same x coordinate, using linear progress for equal horizontal intervals and stroke allowance on the clip because path arc length is not horizontal distance. Its grid, labels, and frame stay still. It holds at 0-10%, sweeps at 10-80%, and holds the finished result at 80-100%. Narrow or short windows and reduced motion receive the finished unpinned layout. Tune its thresholds, phases, and colors to the brief.

```html
<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sample profile</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font: 1rem/1.5 system-ui; color: #182430; background: #f4f6f8; }
  header, footer { padding: 2rem; }
  .pin { display: grid; grid-template-rows: auto minmax(0, 1fr) auto;
    gap: 1rem; padding: 2rem; max-width: 75rem; margin: auto; }
  h1, p { margin: 0; }
  svg { display: block; width: 100%; height: 100%; min-height: 0; }
  .figure { min-height: 0; aspect-ratio: 3 / 1; }
  .scrub { height: 240svh; }
  .scrub .pin { position: sticky; top: 0; height: 100svh; }
  .scrub .figure { aspect-ratio: auto; }
</style>
<header><h1>One sample, one profile</h1><p>The finished profile remains available without motion.</p></header>
<section id="scene">
  <div class="pin">
    <p>The instrument reads the sample from left to right.</p>
    <div class="figure">
      <svg viewBox="0 0 600 200" role="img" aria-label="Illustrative profile with a central peak">
        <defs><clipPath id="reveal" clipPathUnits="userSpaceOnUse">
          <rect id="clip" x="18" y="18" width="564" height="164"/>
        </clipPath></defs>
        <path d="M20 20V180H580" fill="none" stroke="currentColor"/>
        <path d="M20 155L160 120L300 40L440 95L580 70"
          clip-path="url(#reveal)" fill="none" stroke="#245b82" stroke-width="3"/>
        <path id="cursor" d="M580 20V180" stroke="#245b82" stroke-width="2"/>
      </svg>
    </div>
    <p>Illustrative data. The peak occurs near the center of this sample.</p>
  </div>
</section>
<footer>The complete reading can now be compared with another sample.</footer>
<script>
  const scene = document.querySelector('#scene');
  const pin = scene.querySelector('.pin');
  const clip = document.querySelector('#clip');
  const cursor = document.querySelector('#cursor');
  const roomy = matchMedia('(min-width: 48rem) and (min-height: 700px)');
  const motion = matchMedia('(prefers-reduced-motion: no-preference)');
  const clamp = n => Math.max(0, Math.min(1, n));
  let enabled = false, target = 1, p = 1, frame = 0, last = 0;
  function draw() {
    const sweep = clamp((p - .1) / .7);
    const x = 20 + 560 * sweep;
    clip.setAttribute('width', String(x - 18 + 2));
    cursor.setAttribute('d', 'M' + x + ' 20V180');
  }
  function tick(now) {
    p += (target - p) * (1 - Math.exp(-(now - last) / 90));
    last = now;
    if (Math.abs(target - p) < .0004) p = target;
    draw();
    frame = p === target ? 0 : requestAnimationFrame(tick);
  }
  function update(snap = false) {
    const travel = scene.offsetHeight - pin.offsetHeight;
    const next = enabled ? clamp(-scene.getBoundingClientRect().top / Math.max(1, travel)) : 1;
    const jump = Math.abs(next - target) > .25;
    target = next;
    if (snap || jump || next === 0 || next === 1 || !enabled) {
      cancelAnimationFrame(frame); frame = 0; p = target; draw();
    } else if (!frame && p !== target) {
      last = performance.now(); frame = requestAnimationFrame(tick);
    }
  }
  function configure() {
    enabled = roomy.matches && motion.matches && CSS.supports('position', 'sticky');
    scene.classList.toggle('scrub', enabled);
    update(true);
  }
  addEventListener('scroll', () => update(), { passive: true });
  addEventListener('resize', configure);
  roomy.addEventListener('change', configure);
  motion.addEventListener('change', configure);
  new ResizeObserver(() => update(true)).observe(pin);
  document.fonts.ready.then(configure);
  configure();
</script>
</html>
```

The passive listener reads native scroll position without intercepting input. Record that reason if the source linter flags `scroll-listener`, then verify rendering cost in a trace. In production, include the actual sticky-header offset in the height and progress calculations. If copy cannot fit at enlarged text sizes, move it before the pin or disable pinning. Inspect slow and fast scrolling, reversal, anchor jumps, and live resizing; captures alone cannot establish smooth settling.

## Timing and easing

| Change | Starting duration | Starting curve |
|---|---|---|
| Input feedback (press, focus, busy) | Visible on the next rendered frame; measured against a roughly 100 ms response convention | Instant, or the feedback curve below |
| Hover and press transitions | 80-150 ms | `cubic-bezier(0.2, 0, 0, 1)` |
| Small state change (toggle, tab, inline disclosure) | 120-200 ms | `cubic-bezier(0.4, 0, 0.2, 1)` |
| Panel or dialog | 180-300 ms | Decelerating entrance, shorter exit |
| Narrative transition | 300-500 ms, when justified and interruptible | Decelerating |

`cubic-bezier(0.2, 0, 0, 1)` covers half its distance in about the first fifth of the duration and spends the rest settling, which suits entrances and feedback because the change is visible at once. `cubic-bezier(0.4, 0, 0.2, 1)` eases in and out, which suits an element moving between two resting positions. Adapt both to the product's existing motion tokens.

Exits can run shorter than entrances because the user has already decided to leave; a dialog that opens in 280 ms can close in 200 ms. An interrupted or reversed animation continues from its current visual state. CSS transitions do this on their own, while keyframe animations restart from their first keyframe, so use transitions for anything a user can toggle and call `reverse()` on a running Web Animations API animation instead of starting a new one. Input is never locked until an animation finishes. Delays and staggers never gate primary content or actions: if the focal group uses a short sequence, every control in it accepts input from the first frame.

## Feedback and responsiveness

- **Next-frame press feedback is a measured target.** `:active` styles apply at pointer-down, and a free main thread paints them on the next frame, but CSS cannot promise that frame. Record a performance trace on the target device and measure from the input event to the first frame showing the pressed state.
- **Roughly 100 ms is the response convention for press, focus, and busy feedback.** Report each measurement with its conditions (device, browser, build mode, CPU throttling, and input method), because a timing without them cannot be reproduced.
- **Feedback is distinct from completion.** A pressed or busy control says the input was received; a success message says the operation finished and appears only after the operation confirms. Network completion has its own budget, measured separately, and feedback never claims success before success is known.
- **Rendering cost is inspected rather than assumed.** Changes to `transform` and `opacity` can usually be composited without layout or paint, which makes them the default for movement and fades. They still cost memory and compositing time: large layers, many simultaneous layers, and `filter: blur()` or `backdrop-filter` can stay expensive. Animating layout on a small, measured region such as one disclosure row can be justified.
- **The frame budget is small.** At 60 Hz a frame lasts about 16.7 ms (1000 / 60), and script, style, layout, paint, and compositing share it; at 120 Hz it is about 8.3 ms. Input handlers and animation callbacks leave room for the browser's own work.

## Reduced motion

`prefers-reduced-motion: reduce` asks for less movement and never for less information. Reduced motion preserves the final state and everything the animated version shows: replace movement with an instant change or a short opacity change, and keep status that motion conveyed in text or a static indicator. [WCAG 2.2 SC 2.3.3](https://www.w3.org/TR/WCAG22/#animation-from-interactions) (AAA) asks that motion triggered by interaction can be disabled unless the motion itself carries the function or information.

In CSS, prefer opting motion in with `@media (prefers-reduced-motion: no-preference)`, so the static base is what a browser without the media feature gets; the entrance below uses this pattern. Overriding with `@media (prefers-reduced-motion: reduce)` suits existing motion; the hover and press example uses it. A busy indicator keeps a static shape and sits beside visible text such as "Saving", with the indicator marked `aria-hidden="true"`:

```css
.busy {
  display: inline-block; inline-size: 1em; block-size: 1em; vertical-align: -0.125em;
  border: 2px solid currentColor; border-inline-end-color: transparent; border-radius: 50%;
}

@keyframes busy-turn { to { transform: rotate(1turn); } }

@media (prefers-reduced-motion: no-preference) {
  .busy { animation: busy-turn 900ms linear infinite; }
}
```

A CSS media query cannot stop a `requestAnimationFrame` loop, so JavaScript and canvas code reads the preference and listens for changes with `matchMedia(...).addEventListener('change', ...)`. Continuous decay uses elapsed time, `value *= 0.5 ** (deltaSeconds / halfLifeSeconds)`, so a dropped frame or a paused background tab lands on the same value a steady loop would reach. In the example, a canvas meter eases toward a range input's value; reduced motion jumps to the final value, and the `<output>` carries the number in both modes. Adding the change to `gap` keeps the drawn value where it is, so a new input mid-animation continues from the current visual state.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Level meter</title>
</head>
<body>
<label for="level">Level</label>
<input id="level" type="range" min="0" max="100" value="40">
<output id="reading" for="level">40</output>
<canvas id="meter" width="320" height="16" aria-hidden="true"></canvas>
<script>
  const input = document.getElementById('level');
  const reading = document.getElementById('reading');
  const canvas = document.getElementById('meter');
  const context = canvas.getContext('2d');
  const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  const halfLifeSeconds = 0.15;
  let target = Number(input.value);
  let gap = 0, frameId = 0, lastTime = 0;

  function draw() {
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = '#1f4f82';
    context.fillRect(0, 0, (canvas.width * (target - gap)) / 100, canvas.height);
  }

  function frame(now) {
    const deltaSeconds = Math.max(0, now - lastTime) / 1000;
    lastTime = now;
    gap *= 0.5 ** (deltaSeconds / halfLifeSeconds);
    if (Math.abs(gap) < 0.1) gap = 0;
    draw();
    frameId = gap === 0 ? 0 : requestAnimationFrame(frame);
  }

  function settle() { cancelAnimationFrame(frameId); frameId = 0; gap = 0; draw(); }

  input.addEventListener('input', () => {
    const next = Number(input.value);
    gap += next - target;
    target = next;
    reading.value = String(next);
    if (motionQuery.matches) {
      settle();
    } else if (!frameId) {
      lastTime = performance.now();
      frameId = requestAnimationFrame(frame);
    }
  });

  motionQuery.addEventListener('change', (event) => { if (event.matches) settle(); });
  draw();
</script>
</body>
</html>
```

## Orchestrated entrance

Animate one composed focal group, such as the heading, lede, and primary action together, and nothing else on load. The group's base styles are fully visible, so a skipped animation from reduced motion, an engine that ignores the rule, or printing leaves finished content. Never hide content in base CSS and reveal it with a script-added class, because a script failure then leaves a blank region. Avoid repeated per-section fades. A supporting operation may animate when it explains cause and effect, with less emphasis than the peak. The group accepts clicks and keyboard focus while it moves; nothing sets `pointer-events: none` or `inert` during the animation.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Veneer samples</title>
<style>
  body { margin: 0; font-family: system-ui, sans-serif; line-height: 1.5; }
  main { max-inline-size: 60rem; margin-inline: auto; padding: 2rem 1rem; }
  .focal-group h1 { font-size: clamp(2.5rem, 1.5rem + 4vw, 5rem); line-height: 1.05; margin: 0 0 1rem; }
  @keyframes arrive {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: none; }
  }
  @media (prefers-reduced-motion: no-preference) {
    .focal-group { animation: arrive 240ms cubic-bezier(0.2, 0, 0, 1); }
  }
</style>
</head>
<body>
<main>
  <header class="focal-group">
    <h1>Walnut, oak, and ash veneers, cut to your panel size</h1>
    <p>Order a sample set before committing to a full sheet.</p>
    <a href="#samples">Browse samples</a>
  </header>
  <section id="samples" aria-labelledby="samples-title">
    <h2 id="samples-title">Samples</h2>
    <p>Each sample ships with its grain direction marked on the back.</p>
  </section>
</main>
</body>
</html>
```

Check the entrance at normal speed, press the link while the group is still moving, and confirm the group is fully visible and static under reduced motion.

## Hover and press

Use movement on controls whose affordance benefits from it. The first `<style>` block below is the baseline pattern: adaptable token roles plus local press feedback, with the focus color defined so the page runs. Replace `--color-focus` with the project's contrast-checked focus token. The second block completes the move: hover lift only on devices with a fine pointer that can hover, a color response on hover and press, and a reduced-motion override that removes displacement while keeping the color change. The 1px movement and 120 ms duration are examples; stable geometry and immediate acknowledgment are the intended outcomes.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hover and press</title>
<style>
  :root {
    --space-control-x: 1rem;
    --space-control-y: 0.75rem;
    --duration-feedback: 120ms;
    --ease-feedback: cubic-bezier(0.2, 0, 0, 1);
    --color-focus: #1d4ed8;
  }

  .action {
    padding: var(--space-control-y) var(--space-control-x);
    transition: transform var(--duration-feedback) var(--ease-feedback);
  }

  .action:active {
    transform: translateY(1px);
  }

  .action:focus-visible {
    outline: 2px solid var(--color-focus);
    outline-offset: 3px;
  }

  @media (prefers-reduced-motion: reduce) {
    .action { transition: none; }
    .action:active { transform: none; }
  }
</style>
<style>
  body { margin: 0; padding: 2rem; background: #f7f9fc; color: #1b1f24; font-family: system-ui, sans-serif; }
  .action {
    border: 0; border-radius: 0.5rem; background: #1f4f82; color: #f7f9fc; font: inherit;
    transition-property: transform, background-color;
  }
  .action:active { background: #173d66; }
  @media (hover: hover) and (pointer: fine) {
    .action:hover { transform: translateY(-1px); background: #2a5f96; }
    .action:hover:active { transform: translateY(1px); background: #173d66; }
  }
  @media (prefers-reduced-motion: reduce) {
    .action:hover, .action:hover:active { transform: none; }
  }
</style>
</head>
<body>
<button type="button" class="action">Save changes</button>
</body>
</html>
```

In the second block, `transition-property` extends the first block's duration and curve to the background color, and the `:hover:active` rules keep press feedback visible while the pointer hovers. Under reduced motion the first block's `transition: none` sets the duration to zero, so the color still changes, instantly. Check the pressed state with a pointer, the focus ring with the keyboard, and the absence of hover lift on a touch device.

## View transitions

Same-document View Transitions reached Baseline newly available in October 2025, and transition types followed in January 2026; check both against the project's browser floor in the dated platform table in [foundations](foundations.md). The ordinary DOM update is the no-animation path. Detect `document.startViewTransition`, skip the transition under reduced motion, and call the same update either way, so a transition is never required to navigate or finish an action. Do network work before starting the transition, because the page stops rendering new frames until the update callback finishes. Starting a new transition while one runs skips the running one to its end state and rejects its `ready` promise if it has not yet resolved, which the example catches. The update callback runs asynchronously, so the example keeps its state in a variable and passes each callback its target value; reading the DOM at click time would let two quick clicks compute the same target.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sample detail</title>
<style>
  body { margin: 0; padding: 1rem; font-family: system-ui, sans-serif; }
  .sample { view-transition-name: sample; inline-size: 8rem; aspect-ratio: 4 / 3; background: #6f4e37; }
  .expanded .sample { inline-size: min(100%, 32rem); }
  ::view-transition-group(sample) { animation-duration: 280ms; animation-timing-function: cubic-bezier(0.2, 0, 0, 1); }
</style>
</head>
<body>
<main id="view">
  <div class="sample" role="img" aria-label="Walnut veneer sample"></div>
  <button type="button" id="toggle" aria-pressed="false">Enlarge sample</button>
</main>
<script>
  const view = document.getElementById('view');
  const toggle = document.getElementById('toggle');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let expanded = false;
  function render(state) {
    view.classList.toggle('expanded', state);
    toggle.setAttribute('aria-pressed', String(state));
  }
  toggle.addEventListener('click', () => {
    expanded = !expanded;
    const next = expanded;
    if (!document.startViewTransition || reduceMotion.matches) {
      render(next);
      return;
    }
    document.startViewTransition(() => render(next)).ready.catch(() => {});
  });
</script>
</body>
</html>
```

Cross-document transitions are a progressive enhancement: Firefox had no support when checked in September 2026. Both pages include the rule below, the navigation must be same-origin, and links stay ordinary `<a href>` elements, so a browser without support navigates normally. Use no polyfill, no script that intercepts links, and no new dependency.

```css
@view-transition { navigation: auto; }

@media (prefers-reduced-motion: reduce) {
  ::view-transition-group(*), ::view-transition-old(*), ::view-transition-new(*) {
    animation: none !important;
  }
}
```

## Scroll-driven enhancement

Scroll-driven animations were not Baseline when checked in September 2026, and Firefox stable kept them behind a flag. Treat them as an enhancement guarded by both `@supports (animation-timeline: view())` and `prefers-reduced-motion: no-preference`, with content fully visible in base styles. The `animation` shorthand resets `animation-timeline` ([MDN animation-timeline](https://developer.mozilla.org/en-US/docs/Web/CSS/animation-timeline)), so `animation-timeline` and `animation-range` follow the shorthand. The `1ms` duration follows MDN's example, and scroll position drives the progress. Keep the animation and its timeline inside the same guarded block; a shorthand outside it would run as an ordinary time-based animation in unsupported browsers. The `entry` range ends when an element is fully inside the viewport, so a figure shorter than the viewport is at full opacity whenever it is fully in view, including after a jump link or find-in-page; use it on figures or cards of that size.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Grain gallery</title>
<style>
  body { margin: 0; padding: 1rem; font-family: system-ui, sans-serif; }
  .gallery { display: grid; gap: 4rem; max-inline-size: 40rem; margin-inline: auto; }
  .gallery figure { margin: 0; }
  .swatch { aspect-ratio: 3 / 2; background: #6f4e37; }

  @keyframes settle { from { opacity: 0; transform: translateY(1.5rem); } to { opacity: 1; transform: none; } }

  @supports (animation-timeline: view()) {
    @media (prefers-reduced-motion: no-preference) {
      .gallery figure {
        animation: settle 1ms linear both;
        animation-timeline: view();
        animation-range: entry 0% entry 100%;
      }
    }
  }
</style>
</head>
<body>
<main class="gallery">
  <figure><div class="swatch"></div><figcaption>Walnut, quarter sawn</figcaption></figure>
  <figure><div class="swatch"></div><figcaption>White oak, rift sawn</figcaption></figure>
  <figure><div class="swatch"></div><figcaption>Ash, flat sawn</figcaption></figure>
</main>
</body>
</html>
```

## Asynchronous states

- **Reserve geometry.** Give images and media `width` and `height` attributes or an `aspect-ratio`, and give placeholders the dimensions of the content they stand for, so arriving content does not move what the user is reading.
- **Use a skeleton only when it predicts the structure.** A list with a known row shape can show skeleton rows; a result of unknown shape gets a local busy state instead, because a mismatched skeleton adds a layout shift when content arrives.
- **Show progress where the work is.** Put a busy state or determinate progress on the control, row, or panel that started the operation, and keep the surrounding context visible. The static busy indicator in [Reduced motion](#reduced-motion) works in both motion modes.
- **Never add an artificial minimum wait.** A fast result appears when it arrives; a spinner or animation does not earn extra time on screen.
- **Keep optimistic updates to reversible operations.** Starring, renaming, or reordering can update at once when the code keeps the prior state, rolls back on failure, and shows an explicit failure message that names what did not save and offers a retry.
- **Tell the truth on consequential actions.** Deleting, paying, or sending shows a pending state that names the operation and a confirmation only after the server confirms. A second press during the pending state does not repeat the action.
- **Preserve work on retry.** Entered text stays in its fields and focus stays where the user can continue.

The full per-component state matrix, including empty, error, and long-content states, is in [finishing](finishing.md).

## Scroll and control

Keep native scrolling so the user controls position and speed: no script that intercepts wheel, touch, or key input to change speed or jump between sections, and no forced parallax tied to page scroll. A scroll-driven enhancement reads scroll position without controlling it. For a deliberate nested scroll region, use the containment and padding in [foundations](foundations.md#controlled-scroll-regions).

Give extended media its own controls. Video, animated illustration, or auto-updating content that starts on its own, lasts more than five seconds, and sits alongside other content needs a way to pause, stop, or hide it under [WCAG 2.2 SC 2.2.2](https://www.w3.org/TR/WCAG22/#pause-stop-hide) (A). Decoration that animates continuously and competes with reading is removed. No task information is available only on hover: anything shown on hover also appears on keyboard focus and on touch, or stays visible, and content revealed on hover or focus follows [WCAG 2.2 SC 1.4.13](https://www.w3.org/TR/WCAG22/#content-on-hover-or-focus) (AA).

LCP, INP, and CLS budgets, their diagnosis, and their measurement belong to the project's engineering workflow, recorded with device, network, viewport, build mode, method, and whether the evidence is a local trace or field data.

## What a screenshot cannot show

A screenshot shows end states: the settled entrance, a captured hover or pressed state, the focus ring after keyboard focus, and whether placeholders reserve the space their content later fills. It cannot show timing, easing, interruption, press latency, or whether reduced motion actually removes displacement. Timing and latency need a performance trace; interruption needs input sent while an animation runs; a fallback needs a browser without the feature or the feature disabled.

Reduced-motion checks need media emulation (a runtime emulation tool, a browser started with reduced motion set, or the project's browser tests) or source review, and the report states which one was used. A source review is reported as source evidence and never as a rendered check. With emulation active, `document.getAnimations()` in the page lists the animations still running. The rendered verification loop, including widths, captures, and the probe, is in [finishing](finishing.md).
