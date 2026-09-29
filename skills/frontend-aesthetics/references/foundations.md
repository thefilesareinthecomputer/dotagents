# Foundations: direction, systems, and named moves

Read this reference when selecting or auditing a visual system, before writing tokens or markup. It turns a brief into a committed direction, a small token system, and concrete CSS moves, each paired with the rendered check that shows whether it worked. [interaction.md](interaction.md) owns motion, timing, feedback, and async behavior. [finishing.md](finishing.md) owns the state matrix, content stress checks, and the rendered verification loop. [tells.md](tells.md) owns lint interpretation.

**Contents**

- [How values are labeled](#how-values-are-labeled)
- [Direction first](#direction-first)
- [The three dials](#the-three-dials)
- [Qualities and evidence](#qualities-and-evidence)
- [Layout and grouping](#layout-and-grouping)
- [Layered compositions](#layered-compositions)
- [Typography](#typography)
- [Color and contrast](#color-and-contrast)
- [Depth and surface](#depth-and-surface)
- [Assets](#assets)
- [Responsive behavior and target size](#responsive-behavior-and-target-size)
- [Named moves](#named-moves): [optical display type](#optical-display-type), [stable numeric columns](#stable-numeric-columns), [deliberate wrapping](#deliberate-wrapping), [tonal surface steps](#tonal-surface-steps), [two-layer depth](#consistent-two-layer-depth), [intrinsic repetition](#intrinsic-repetition), [aligned card internals](#aligned-card-internals), [asymmetric composition](#asymmetric-composition), [orchestrated entrance](#one-orchestrated-entrance), [hover and press](#local-hover-and-press-response), [controlled scroll regions](#controlled-scroll-regions), [container-aware components](#container-aware-components), [relationship styling with :has()](#relationship-styling-with-has)
- [Platform capabilities](#platform-capabilities)

## How values are labeled

Every recommended value here is one of three kinds. Each value, table, or code block is labeled once instead of repeating caveats.

- **Requirement.** A value the brief, brand, design system, or browser floor already fixes. It is binding and overrides every convention in this reference.
- **Baseline (SC n.n.n).** An accessibility minimum from WCAG 2.2, cited by success criterion. Meeting it does not establish conformance, and contrast and target size are not a complete accessibility checklist. Engineering owns semantics, accessible names, announcements, and interaction correctness.
- **Convention.** A starting value. Adjust it with a stated reason, such as the chosen font, the real content, or a dense tool's needs.

Values inside code blocks are conventions unless a comment says otherwise. Example palettes and hues are placeholders; replace them with the product's own.

## Direction first

Commit to a direction before choosing tokens. A direction is one sentence about this subject that the rest of the system serves; a style word such as "minimal" or "bold" does not qualify.

Use [art direction](art-direction.md) to name the peak, allocate emphasis, reject generic defaults, and carry the subject through the page. Prove the hero and peak before repeating sections. A local refinement carries the existing direction; an audit assesses it without replacing it. An established system can supply the direction, and a settings screen does not need a new hero or identity.

### Example: a materials catalog

- **Content.** A supplier's catalog of stone, timber, and textile samples. Each entry has a high-resolution photograph of the surface, a name, a finish, dimensions, and lead time. Buyers choose by texture and color at close range and read specifications second.
- **Direction.** The material's surface is the page: one large, close-cropped image of the grain carries each entry, and restrained supporting type stays out of its way. A visitor remembers the texture.
- **Generic alternative rejected.** A centered headline over a wide lifestyle photo, then a grid of equal product cards with drop shadows and identical buttons. It hides the one thing buyers came to judge.
- **Moves.** [Asymmetric composition](#asymmetric-composition) at two thirds image and one third specifications, [tonal surface steps](#tonal-surface-steps) at near-zero chroma so the canvas does not tint the material, [stable numeric columns](#stable-numeric-columns) for dimensions, and body-sized type with one modest heading. Dials (variance / motion / density): 7 / 2 / 3.
- **Inspect.** At 320 and 1440 CSS px the crop still shows grain instead of background. The image is sharp at its rendered size on a 2x display. The neutral canvas does not shift the material's color. At 320 CSS px the name and finish follow the image directly.

### Example: an operational queue

- **Content.** An internal support queue inside an existing product. Each row has a title, status, age, owner, and next action. Operators work through a long list each shift, compare status and age down the list, and act on one row at a time. The brand tokens and system font are requirements.
- **Direction.** The next decision is the page: status and next-action columns align down the whole queue, so an operator scans one column and acts from the other, inside the existing brand. A visitor remembers how fast the next action is to find.
- **Generic alternative rejected.** A row of stat cards with sparklines above a card-per-ticket list, restyled with a new accent color. It spends the first screen on summaries and breaks column alignment.
- **Moves.** [Stable numeric columns](#stable-numeric-columns) for age and counts, aligned rows with light separators, status as text and shape as well as color, [controlled scroll regions](#controlled-scroll-regions) under a sticky column header, and local press feedback only. Dials (variance / motion / density): 3 / 2 / 8.
- **Inspect.** Columns stay aligned with long titles and large counts. Status reads without color. The next-action column is visible at 1024 CSS px without horizontal page scrolling. At 320 CSS px each row stacks with status and next action first. No brand token changed.

## The three dials

The dials communicate intent; they do not grade quality. State each value with its reason and the decision it drives, for example `DESIGN_VARIANCE 7: the image column takes two thirds of the width`.

| Dial | Low and high anchors | Contextual consequence |
|---|---|---|
| `DESIGN_VARIANCE` | At 1, favor regular alignment and equal relationships; at 10, favor asymmetry and deliberate spatial contrast. | Increase the focal column's share when content priority warrants it. No value prohibits a centered composition that fits the brief. |
| `MOTION_INTENSITY` | At 1, favor static presentation and local feedback; at 10, allow coordinated narrative motion. | A walkthrough can justify one choreographed moment, while an operational queue can keep local feedback only. Every value preserves reduced-motion access. |
| `VISUAL_DENSITY` | At 1, favor generous separation; at 10, favor compact information and frequent comparisons. | A dense queue can use aligned rows, tabular figures, and light separators. Density does not require a monospace font or prohibit cards. |

No dial value bans a centered layout, forces motion, requires a monospace font, or removes cards. A high `MOTION_INTENSITY` permits motion and never requires motion the content does not need. At every value, motion that the task does not depend on gets a reduced-motion treatment, which [interaction.md](interaction.md) specifies.

These settings are starting points that the brief, content, and existing system move:

| Brief | Variance / Motion / Density | Starting reason |
|---|---|---|
| Editorial reading page | 5 / 3 / 3 | Type carries the direction. Measure and leading matter more than layout contrast, and motion stays local. |
| Brand or launch page | 7 / 6 / 3 | One focal image or display treatment takes the dominant share, and one orchestrated entrance can carry it. |
| Data-dense tool | 4 / 2 / 8 | Aligned rows, tabular figures, and light separators; feedback stays local. Cards remain valid for grouped summaries. |
| Public-sector service | 3 / 2 / 5 | Predictable alignment and plain hierarchy serve task completion. A centered single column is often the right composition. |

## Qualities and evidence

Each quality leads to techniques and to evidence a reviewer can check. None defines a mandatory style.

| Quality | Techniques | Reviewer evidence |
|---|---|---|
| Modern | Rem-bounded `clamp()` type, [intrinsic grids](#intrinsic-repetition), [container-aware components](#container-aware-components), and semantic tokens, with capabilities chosen through the [dated support policy](#platform-capabilities). | The same task is clear on narrow and wide screens. Type and layout adapt without clipping or device-specific decoration. Existing branding stays recognizable. |
| Premium | Deliberate display tracking and optical sizing, [tabular figures](#stable-numeric-columns) for changing values, [tonal surface steps](#tonal-surface-steps) with one light direction, room for primary content, and every applicable state finished. | Repeated elements align, spacing reflects grouping, icons and imagery form one family, and loading and failure get the same attention as the default state. |
| High-end | The committed direction delivered through a dominant type treatment, focal image, [asymmetric composition](#asymmetric-composition), or interactive moment, with disciplined supporting elements. | Each distinctive choice ties to the product and content. Imagery is sharp at rendered size, crops keep the subject, and ambition does not hide the task or delay access. |
| Refined | A controlled scale, optical corrections, stable baselines, consistent borders and radii, [deliberate wrapping](#deliberate-wrapping), and small documented adjustments where mathematical alignment looks wrong. | States keep alignment and dimensions. Text wraps intentionally with real content. Icon weight and baseline fit adjacent text. No unexplained local exceptions remain. |
| Snappy | Local press feedback on the next rendered frame, explicit short transitions, reserved loading geometry, and feedback kept distinct from completion; [interaction.md](interaction.md) holds the budgets. | Feedback is measured under stated conditions. Repeated actions stay responsive, failures preserve work, and delays leave no ambiguous button or form state. |
| Immersive | A recognizable focal element whose spatial and subject relationships carry through navigation and state changes. An experiential brief gets one orchestrated moment or a supported view transition; a static focal composition is also a deliberate direction. | The focal element delivers the promised experience without competition. Orientation persists between states, scrolling stays user-controlled, and reduced-motion users get equivalent information. An expressive brief with no discernible direction needs revision. |

## Layout and grouping

Start from content priority and one shared alignment grid. Use grid for two-dimensional relationships and flex for one-dimensional runs, with intrinsic sizing and flexible tracks. Related items sit closer together than separate groups do. The scale of 4, 8, 12, 16, 24, 32, 48, and 64 CSS px is a convention; an established project scale is a requirement.

```css
:root {
  --space-1: 0.25rem; --space-2: 0.5rem; --space-3: 0.75rem; --space-4: 1rem;
  --space-5: 1.5rem; --space-6: 2rem; --space-7: 3rem; --space-8: 4rem;
}
.field { display: grid; gap: var(--space-2); } /* label to input: inside a group */
.form { display: grid; gap: var(--space-6); }  /* field to field: between groups */
```

1px borders and 2px optical corrections sit outside the scale and need no token. Dense tools use the small end of the scale inside rows; editorial pages use the large end between sections. Inspect repeated edges and grouping at real widths: a gap inside a group that equals the gap between groups erases the grouping.

## Layered compositions

Keep copy and actions in flow. Give artwork its own grid row or area with a reserved aspect ratio, then layer inside that area. Anchor coupled graphics to one containing block and coordinate system; independent viewport percentages for a beam, aperture, and cursor drift as text wraps. Put related SVG parts in one `viewBox`, with explicit `userSpaceOnUse` clip and mask coordinates. Map necessary HTML overlays through `getScreenCTM()` into their containing block.

Budget hero height before sizing its parts: navigation + vertical padding + headline lines times line-height + copy/actions + artwork rows + gaps must fit the usable viewport when promising a full-screen composition. In shared rows, count the tallest occupant once. For a 900px window, a starting budget could be 64px navigation, 64px padding, 240px headline, 112px copy/actions, 280px artwork, and 64px gaps, totaling 824px. Recalculate at 640px tall; reduce gaps, recompose into columns, or allow ordinary scrolling. Never force a `min-height` taller than the window or clip readable content to preserve the promise.

Use height-aware bounds such as `clamp(3.5rem, min(2rem + 7vw, 16svh), 10rem)` for expressive display type, then inspect actual wrapping and zoom. On short windows, remove fixed hero heights and pinning. Scale the artwork's allocated grid area with the artwork so a smaller drawing leaves no empty band. Reflow copy and artwork together at collision breakpoints. Allow bleed only across named boundaries clear of copy and controls; inspect filter extents and enclosing overflow. Refresh geometry on `ResizeObserver` and after `document.fonts.ready` without replaying entrances.

## Typography

Name five roles and give each a token. For an expressive page, choose a real display face and test headlines against the hero height budget. The compact h1 example below serves application hierarchy; choose the display role for a launch headline. The values are conventions to test against the actual font.

| Role | Starting values | Notes |
|---|---|---|
| Display | `clamp(2.5rem, 1.5rem + 4vw, 6rem)`, line-height 1.05, tracking about -0.02em above 40 CSS px | See [optical display type](#optical-display-type); for launch headlines, use the height-aware clamp in [Layered compositions](#layered-compositions). |
| Heading | Steps of a 1.2 or 1.25 scale from body, line-height 1.05-1.25 | Tighten leading as size grows when the font and wrapping support it. |
| Body | 16-18 CSS px, line-height 1.45-1.65, normal tracking, 45-75 characters per line | Dense controls can run smaller and tighter than prose. |
| Label | One step below body; about 0.03em tracking only on existing small-cap labels | Tracking never manufactures all-caps labels. |
| Numeric | `font-variant-numeric: tabular-nums` where values change or align | A monospace family is optional. |

```css
:root {
  --font-text: system-ui, sans-serif; /* placeholder: the project's families */
  --text-label: 0.8rem; --text-body: 1rem; --text-h3: 1.25rem; --text-h2: 1.5625rem; --text-h1: 1.9531rem;
}
body { font-family: var(--font-text); font-size: var(--text-body); line-height: 1.55; }
h1 { font-size: var(--text-h1); line-height: 1.1; }
h2 { font-size: var(--text-h2); line-height: 1.15; }
h3 { font-size: var(--text-h3); line-height: 1.25; }
.prose { max-inline-size: 65ch; }
```

`ch` is the width of the zero glyph, so `65ch` only approximates the measure; count characters in rendered lines to confirm. Use relative units and bounded fluid sizes. Text sized only in viewport units does not grow with browser zoom, so every `clamp()` keeps rem bounds and a rem term in its middle value; text must resize to 200% without loss of content or function (baseline, [SC 1.4.4](https://www.w3.org/TR/WCAG22/#resize-text)). System fonts can be an intentional choice. Test the actual font, its fallback, the weights in use, real content, and zoom. At 320 CSS px with real content, heading levels must still read as distinct steps above body text, and tracking must not cause collisions.

## Color and contrast

Define semantic roles before any hue. The palette below is a placeholder, written in hex so the contrast helper can measure it; replace every value with the product's colors.

```css
:root {
  --color-canvas: #f4f5f7; --color-surface: #ffffff; --color-surface-raised: #ffffff;
  --color-text: #1b1d21; --color-text-muted: #555b66;
  --color-border-decorative: #c9ced6; --color-border-control: #767d89;
  --color-accent: #2952cc; --color-focus: #1a4fd6;
  --color-danger: #b42318; --color-success: #1e7a3e;
}
```

The baselines, read from the [WCAG 2.2 Recommendation](https://www.w3.org/TR/WCAG22/) on 2026-09-26:

- **Text: 4.5:1** (baseline, [SC 1.4.3](https://www.w3.org/TR/WCAG22/#contrast-minimum)). Large-scale text needs **3:1**. WCAG defines large-scale text as at least 18 point, or 14 point bold. The figures 24 CSS px and about 18.67 CSS px bold are conversions at 1 pt = 4/3 CSS px; the normative wording uses points. Incidental text and logotypes have no requirement.
- **Non-text: 3:1 against adjacent colors** (baseline, [SC 1.4.11](https://www.w3.org/TR/WCAG22/#non-text-contrast)) for visual information needed to identify components and their states, and for parts of graphics needed to understand content. Inactive components, unmodified user-agent appearance, and graphics whose particular presentation is required for the information are excepted. A focus indicator identifies a state, so measure it against this baseline.

Measure explicit opaque pairs with the helper, run from the skill directory:

```bash
python3 scripts/check_contrast.py --foreground '#rrggbb' --background '#rrggbb' --minimum 4.5
python3 scripts/check_contrast.py --foreground '#555b66' --background '#f4f5f7' --minimum 4.5
```

The second command prints `#555b66 on #f4f5f7: 6.26:1 (minimum 4.5) PASS` and exits 0; a failing pair exits 1 and invalid input exits 2. The placeholder `#c9ced6` border measures 1.58:1 on white, which is why it is decorative only, while `#767d89` measures 4.15:1 and can mark a control boundary. The helper accepts only opaque `#RGB` or `#RRGGBB`. It cannot resolve inheritance, transparency, gradients, or images, and it cannot decide whether text qualifies as large.

- Measure resolved pairs in every supported theme and in each state: hover, selected, disabled, and error. Treat text over images, transparency, and gradients as a rendered composite and inspect it in the browser through the loop in [finishing.md](finishing.md).
- Give status text, shape, or an icon as well as color.
- Brand colors and pure black or white are legitimate when the brief calls for them and the pairs measure. A legacy lint finding against them is resolved by recording the reason, as [tells.md](tells.md) describes.
- Leave a validated chart palette alone; the dataviz skill owns it.

## Depth and surface

Define three elevations: base for the canvas, raised for panels and cards, and overlay for menus, popovers, and dialogs. Choose the separator by what it communicates. A border shows containment in dense layouts, a tonal step relates adjacent regions, and a shadow shows stacking or interaction. Keep one light direction, from above, so every shadow falls downward. The moves are [tonal surface steps](#tonal-surface-steps) and [consistent two-layer depth](#consistent-two-layer-depth).

- An overlay reads above its parent at every width.
- Noninteractive content gets no shadow-and-lift combination that makes it look clickable.
- Dark themes get their own review. Shadows read weakly on dark surfaces, so raise surface lightness with elevation instead.
- Judge glass, blur, gradients, and large shadows by text legibility on the rendered composite and by measured rendering cost. `backdrop-filter` over a large area can be expensive to paint.

## Assets

- Use one image treatment per surface (one crop logic, one color grade, one corner treatment) and one icon family (one grid, one stroke width, `currentColor`).
- Reserve media space with `width` and `height` attributes or `aspect-ratio` so loading does not shift layout. Set the focal point with `object-position`, and supply enough pixels for the rendered size and device pixel ratio through `srcset` and `sizes`.
- Write alt text that names what the image shows; a decorative image gets `alt=""`.
- Label mock data and placeholder images honestly, and do not add imagery only to fill space. Use tabular figures where repeated numbers must align.

```html
<img class="focal-media" src="slate-1600.jpg" width="1600" height="1200"
  srcset="slate-800.jpg 800w, slate-1600.jpg 1600w, slate-2400.jpg 2400w" sizes="(min-width: 48rem) 66vw, 100vw"
  alt="Honed slate surface with fine gray veining">
```

```css
.focal-media {
  display: block; inline-size: 100%; block-size: auto; aspect-ratio: 4 / 3;
  object-fit: cover; object-position: 40% 55%; /* keep the veining in frame when cropped */
}
```

Review crops at 320 and 1440 CSS px, loading on a slow connection, the alt text, icon alignment against adjacent text, and repeated numeric columns.

## Responsive behavior and target size

Set breakpoints where the content breaks and name them after the content change. Check 320, 768, 1024, and 1440 CSS px plus widths around each actual layout transition (convention). At 320 CSS px wide, content must work without scrolling in two dimensions (baseline, [SC 1.4.10](https://www.w3.org/TR/WCAG22/#reflow)); parts that need two-dimensional layout, such as maps, diagrams, and data tables, are excepted and need their own accessible scroll region. Also check 200% zoom, content order, text expansion, focus visibility, sticky elements, mobile browser chrome, safe areas where relevant, and coarse pointers. A sticky header must not entirely hide the focused control (baseline, [SC 2.4.11](https://www.w3.org/TR/WCAG22/#focus-not-obscured-minimum)). Hover-revealed content follows the rule in [interaction.md](interaction.md#scroll-and-control).

Target size has three distinct values, verified against the W3C text on 2026-09-26:

| Level | Minimum | Exceptions |
|---|---|---|
| AA, [SC 2.5.8 Target Size (Minimum)](https://www.w3.org/TR/WCAG22/#target-size-minimum) | 24 by 24 CSS px (baseline) | Five. `Spacing`: an undersized target passes if a 24 CSS px diameter circle centered on its bounding box intersects no other target and no other undersized target's circle. `Equivalent`: another control on the same page that meets the criterion achieves the function. `Inline`: the target is in a sentence or its size is constrained by the line-height of non-target text. `User Agent Control`: the browser sets the size and the author has not modified it. `Essential`: a particular presentation is required for the information or legally required. |
| AAA, [SC 2.5.5 Target Size (Enhanced)](https://www.w3.org/TR/WCAG22/#target-size-enhanced) | 44 by 44 CSS px (baseline at AAA) | Four. `Equivalent`: an equivalent link or control on the same page is at least 44 by 44 CSS px. `Inline`: the target is in a sentence or block of text. `User Agent Control`, as above. `Essential`: a particular presentation is required for the information. There is no spacing exception. |
| Comfort | About 44 by 44 CSS px for primary touch controls (convention) | A comfort convention only. |

Padding or a minimum size enlarges the target without enlarging the icon:

```css
.icon-button {
  display: inline-grid; place-items: center; padding: 0; border: 0; background: transparent;
  min-inline-size: 2.75rem; min-block-size: 2.75rem; /* 44px comfort convention; the AA floor is 24px */
}
.icon-button svg { inline-size: 1.25rem; block-size: 1.25rem; }
```

## Named moves

Each move gives runnable CSS, when it applies, when it does not, and what to inspect in the rendered result. Values are conventions, and placeholder colors and hues get replaced with the product's. [finishing.md](finishing.md) runs these checks across states and widths.

### Optical display type

```css
.display {
  font-size: clamp(2.5rem, 1.5rem + 4vw, 6rem);
  line-height: 1.05; letter-spacing: -0.02em; font-optical-sizing: auto;
}
.label { font-size: 0.8rem; letter-spacing: 0.03em; } /* only where small-cap labels already exist */
```

- **Use when** a display heading carries the direction and you have inspected the chosen font at display size. `font-optical-sizing: auto` is the initial value: declaring it documents intent and undoes a reset, and it changes nothing unless the font has an `opsz` axis.
- **Skip** tight tracking on body text, on fonts already spaced tightly at large sizes, and in dense tools where headings act as labels.
- **Check** the actual and fallback fonts for letter collisions, wrapping at 320 CSS px, and 200% zoom.

### Stable numeric columns

```css
.value { font-variant-numeric: tabular-nums; text-align: end; }
```

- **Use when** totals, counters, timers, or comparable columns change or must align, and the font supplies tabular figures. A monospace family is optional.
- **Skip** numbers in running prose, where proportional figures read better.
- **Check** that a value keeps its width across digit changes and that decimals align down the column. If widths still shift with the declaration applied, the font lacks tabular figures.

### Deliberate wrapping

```css
.heading { text-wrap: balance; }
@supports (text-wrap: pretty) { .prose { text-wrap: pretty; } }
```

- **Use** `balance` on short headings, captions, and pull quotes, and `pretty` on prose as an enhancement that avoids short last lines. Ordinary wrapping is the fallback for both.
- **Skip** `balance` on long paragraphs, since browsers cap how many lines they balance, and never insert forced line breaks to fix one screenshot width.
- **Check** real headlines and long words at 320 CSS px, and the plain path in a browser without `pretty`.

### Tonal surface steps

```css
:root { /* placeholder hue and lightness levels: replace with the product's palette */
  --canvas: oklch(96% 0.015 250); --surface: oklch(98% 0.015 250); --raised: oklch(100% 0.015 250);
}
body { background: var(--canvas); }
.panel { background: var(--surface); border: 1px solid color-mix(in oklch, currentColor 12%, transparent); }
.panel-raised { background: var(--raised); }
```

- **Use when** related regions need separation without a border or shadow on everything. Hold hue and chroma fixed and step lightness.
- **Skip** the mixed border wherever a control boundary must meet 3:1 (baseline, SC 1.4.11); it is decorative and unmeasured.
- **Check** resolved pairs in every theme. `oklch(100% ...)` with nonzero chroma is outside sRGB, so the browser maps it into gamut and the top step can land closer to its neighbor than planned. Convert resolved colors to hex before running the helper.

### Consistent two-layer depth

```css
:root {
  --shadow-raised: 0 1px 2px rgb(0 0 0 / 0.08), 0 8px 24px rgb(0 0 0 / 0.12);
  --shadow-overlay: 0 2px 4px rgb(0 0 0 / 0.1), 0 16px 48px rgb(0 0 0 / 0.18);
}
.raised { box-shadow: var(--shadow-raised); }
.overlay { box-shadow: var(--shadow-overlay); }
```

- **Use when** elevation explains containment or interaction. A small contact shadow plus a broader ambient shadow, both offset downward, keeps one light direction.
- **Skip** elevation on every block, and on dark surfaces where a lighter surface step reads better.
- **Check** that overlays read above raised panels and that no static block looks clickable.

### Intrinsic repetition

```css
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); gap: 1.5rem; }
```

- **Use when** comparable items should decide how many columns fit. `min(100%, 18rem)` keeps a single column from overflowing a narrow container. Repetition is legitimate for comparable objects.
- **Skip** it for content with a clear priority order; use [asymmetric composition](#asymmetric-composition) instead. `auto-fit` stretches a sparse grid's items across the row; switch to `auto-fill` when items should keep their width.
- **Check** sparse and full grids with real content at every checked width.

### Aligned card internals

```html
<div class="cards">
  <article class="card">
    <h3>Honed slate</h3>
    <p>Matte finish with fine gray veining, suited to floors and counters.</p>
    <a href="/samples/honed-slate">Order a sample</a>
  </article>
  <article class="card">
    <h3>Brushed oak with a longer name that wraps onto two lines</h3>
    <p>Wire-brushed grain.</p>
    <a href="/samples/brushed-oak">Order a sample</a>
  </article>
</div>
```

```css
.cards {
  display: grid; grid-auto-rows: auto; gap: 1.5rem;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr));
}
.card {
  display: grid; grid-row: span 3; grid-template-rows: subgrid; row-gap: 0.5rem;
  padding: 1.25rem; border: 1px solid var(--color-border-decorative, #c9ced6);
}
.card > * { margin: 0; }
```

- **Use when** cards in a row share the same parts and headings, descriptions, and actions should align across the row. Each card spans three parent rows because it has three children; change the span when the part count changes.
- **Skip** it when cards hold different kinds of content, or when a card's parts vary in number.
- **Check** long headings and descriptions, and confirm that the DOM reading order still matches the visual order.

### Asymmetric composition

```css
.composition { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 2rem; }
@media (max-width: 48rem) { .composition { grid-template-columns: minmax(0, 1fr); } }
```

- **Use when** the subject or primary task deserves more space than supporting material. Put the focal element first in the DOM so the stacked layout keeps it first, and choose the ratio and the collapse point from the content.
- **Skip** it when the brief calls for symmetry, as a public-service form often does, or when the items are peers.
- **Check** focal priority and reading order in both the two-column and stacked layouts.

### One orchestrated entrance

Use one composed entrance on the focal group when the direction calls for motion, such as a launch page or walkthrough at a higher `MOTION_INTENSITY`. It replaces repeated per-section fades, and the base state stays fully visible so the entrance never delays access. [interaction.md](interaction.md#orchestrated-entrance) holds the code, timing, easing, interruption, and reduced-motion detail.

### Local hover and press response

Use a small displacement or color response on controls whose affordance benefits from movement, such as primary actions. Keep the response local to the control, pair it with visible keyboard focus, and measure press feedback in the browser instead of promising it from CSS. [interaction.md](interaction.md#hover-and-press) holds the code, timing, easing, and reduced-motion detail.

### Controlled scroll regions

```html
<section class="results" aria-labelledby="results-title" tabindex="0">
  <h2 id="results-title" class="results-header">Open tickets</h2>
  <ol class="results-list">
    <li id="ticket-1001"><a href="/tickets/1001">Refund request waiting on review</a></li>
    <li id="ticket-1002"><a href="/tickets/1002">Invoice address change</a></li>
  </ol>
</section>
```

```css
html { scroll-padding-block-start: 4rem; } /* height of a sticky site header */
.results {
  --sticky-offset: 3.5rem; /* match the rendered height of .results-header */
  max-block-size: 32rem; overflow: auto; overscroll-behavior: contain;
  scroll-padding-block-start: var(--sticky-offset, 1rem);
}
.results-header { position: sticky; top: 0; margin: 0; padding-block: 1rem; background: var(--color-surface, #ffffff); }
.results-list { margin: 0; }
```

- **Use** containment on a deliberate nested scroll region, such as a results list or side panel, to stop scroll chaining into the page. Use scroll padding to keep targets clear of sticky chrome at both the page and the region.
- **Skip** containment on every scroller and on the page itself. A region that users expect to hand off to the page should keep default chaining.
- **Check** keyboard scrolling inside the labeled region, touch scrolling past the region's end (the page must not move), and a link to `#ticket-1002` landing below the sticky header.

### Container-aware components

```html
<div class="module">
  <article class="module-layout">
    <img src="oak-800.jpg" width="800" height="600" alt="Brushed oak board, close crop of the raised grain">
    <div class="module-body"><h3>Brushed oak</h3><p>Wire-brushed surface with a raised grain.</p></div>
  </article>
</div>
```

```css
.module { container-type: inline-size; }
.module-layout { display: grid; gap: 1rem; }
.module-layout img { display: block; inline-size: 100%; block-size: auto; }
@container (min-width: 32rem) {
  .module-layout { grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); align-items: start; }
}
```

- **Use when** a reusable component appears in containers of different widths, such as a sidebar and a main column. The query styles `.module-layout` inside `.module`, never the container itself, and the single-column base stays usable.
- **Skip** it for page-level layout keyed to the viewport, and do not replace a working component only to adopt the feature. `container-type: inline-size` ignores content when sizing the container's width, so a shrink-to-fit parent can collapse it.
- **Check** the same component in a narrow and a wide container at one viewport width, and the base layout with the query removed.

### Relationship styling with :has()

```html
<fieldset class="filters">
  <legend>Finish</legend>
  <label class="filter"><input type="checkbox" name="finish" value="honed"> Honed</label> <label class="filter"><input type="checkbox" name="finish" value="brushed"> Brushed</label>
</fieldset>
<div class="field">
  <label for="email">Email</label>
  <input id="email" type="email" aria-invalid="true" aria-describedby="email-error">
  <p id="email-error">Enter an email address.</p>
</div>
```

```css
.filters { display: flex; flex-wrap: wrap; gap: 0.5rem; border: 0; padding: 0; }
.filter {
  display: inline-flex; align-items: center; gap: 0.5rem;
  padding: 0.5rem 0.75rem; border: 1px solid #767d89; border-radius: 999px;
}
.filter:has(input:checked) { border-color: #2952cc; background: #e8eefc; }
.filter:has(input:focus-visible) { outline: 2px solid #1a4fd6; outline-offset: 2px; }
.field:has([aria-invalid="true"]) input { border: 2px solid #b42318; }
```

- **Use when** a container should reflect the state of something inside it: a selected chip, an invalid field, a card with or without media. The semantic state stays where it is. The checkbox remains the control, and engineering sets `aria-invalid`; the selector only styles state that already exists.
- **Skip** it as a substitute for labels, roles, or keyboard behavior. Page-wide selectors anchored on `body` or `:root` can be costly on large, frequently changing pages, so scope them to a component and measure.
- **Check** toggling by keyboard and pointer, the visible focus ring around the chip, and that each checkbox still shows its own state with the `:has()` rules removed.

## Platform capabilities

Checked 2026-09-26. Baseline newly available means a feature works in the current core browsers; widely available follows 30 months later. Before relying on a row, re-check its source, record the new date, and compare the result with the project's browser floor and embedded webviews. Baseline status never overrides a project's older-browser contract. The use policy for each tier comes after the table.

| Capability | Tier | Status on 2026-09-26 | Source |
|---|---|---|---|
| Container size queries | Widely available | Corrected: newly available Feb 2023; widely available Aug 2025. | [MDN @container](https://developer.mozilla.org/en-US/docs/Web/CSS/@container) |
| Subgrid | Widely available | Corrected: newly available Sep 2023; widely available Mar 2026. | [MDN subgrid](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_grid_layout/Subgrid) |
| `:has()` | Widely available | Newly available Dec 2023. Widely available about Jun 2026 by the 30-month rule, derived and not read from a banner. | [MDN :has()](https://developer.mozilla.org/en-US/docs/Web/CSS/:has) |
| `oklch()`, `color-mix()` | Widely available | Partly verified: Baseline 2023, month unconfirmed. Any 2023 month plus 30 months falls before the check date. | [web.dev Baseline 2023](https://web.dev/blog/baseline2023) |
| `text-wrap` property, `balance` value | Newly available | Verified: newly available Mar 2024. Does not cover `pretty`. | [MDN text-wrap](https://developer.mozilla.org/en-US/docs/Web/CSS/text-wrap) |
| Same-document View Transitions | Newly available | Verified: newly available 2025-10-14 with Firefox 144. View transition types reached Baseline newly available in Jan 2026, so reports that Firefox lacks types are out of date. | [web.dev](https://web.dev/blog/same-document-view-transitions-are-now-baseline-newly-available), [MDN :active-view-transition-type](https://developer.mozilla.org/docs/Web/CSS/Reference/Selectors/:active-view-transition-type) |
| `text-wrap: pretty` | Progressive enhancement | Verified: Chrome 117, Safari 26, no Firefox; not Baseline. | [WebKit](https://webkit.org/blog/16547/better-typography-with-text-wrap-pretty/), [MDN text-wrap](https://developer.mozilla.org/en-US/docs/Web/CSS/text-wrap) |
| Scroll-driven animations | Progressive enhancement | Verified: not Baseline; Firefox 152 stable still behind a flag. | [MDN animation-timeline](https://developer.mozilla.org/en-US/docs/Web/CSS/animation-timeline) |
| Cross-document View Transitions | Progressive enhancement | Verified: no Firefox support. | [Chrome blog](https://developer.chrome.com/blog/view-transitions-in-2025), [web.dev](https://web.dev/blog/same-document-view-transitions-are-now-baseline-newly-available) |
| `font-optical-sizing` | Unverified | Date unverified. Keep it labeled and test the font's `opsz` axis. | [MDN font-optical-sizing](https://developer.mozilla.org/en-US/docs/Web/CSS/font-optical-sizing) |
| `overscroll-behavior`, `scroll-padding` | Unverified | Dates unverified. `scroll-padding-inline` alone is widely available since Sep 2021. | [MDN overscroll-behavior](https://developer.mozilla.org/en-US/docs/Web/CSS/overscroll-behavior), [MDN scroll-padding-inline](https://developer.mozilla.org/en-US/docs/Web/CSS/scroll-padding-inline) |

- **Widely available.** Use directly once support is confirmed for the project's browser floor; no extra fallback is needed within that floor. Verify each feature actually used, including query types and property values.
- **Newly available.** Keep the ordinary result as the plain path. Unbalanced headings are acceptable without `balance`. A View Transition is never required to navigate or complete an action; [interaction.md](interaction.md) covers detection and reduced motion.
- **Progressive enhancement.** Guard with `@supports` for the property and value in use, or rely on ignored declarations with a complete plain fallback. Test without the feature and with reduced motion. Ordinary wrapping, static content, and normal navigation keep all information and controls. Treat the listed versions as a dated report to re-verify; they do not define a project's browser floor.
- **Unverified.** Treat as progressive enhancement until someone checks the source and records the date. The declarations in these moves degrade to default behavior when unsupported.

Property support does not establish value support. The `text-wrap` property is newly available while `text-wrap: pretty` is not, which is why the [deliberate wrapping](#deliberate-wrapping) move tests the value with `@supports (text-wrap: pretty)`. Likewise, container size query support says nothing about style or scroll-state queries; verify each query type a component uses.
