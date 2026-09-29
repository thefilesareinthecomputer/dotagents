# The tells

A catalog of patterns that often make a UI read as generic, and the reference for interpreting `scripts/slop_check.py`. It is adapted from `Leonxlnx/taste-skill` (MIT, read 2026-07-14) and reorganized around one question: can a machine count this? Countable patterns are checked by the linter. Judgment patterns are prompts for a human or reviewing agent and are labeled as such. [foundations.md](foundations.md) owns the positive visual system, and [finishing.md](finishing.md) owns rendered verification.

## Contents

- [Why slop happens](#why-slop-happens)
- [Tier 1 - countable (enforced by the linter)](#tier-1---countable-enforced-by-the-linter)
- [Craft checks](#craft-checks)
- [Handling findings](#handling-findings)
- [Tier 2 - judgment (human/agent review)](#tier-2---judgment-humanagent-review)
- [Rules deliberately NOT adopted](#rules-deliberately-not-adopted)

## Why slop happens

A tell is a default standing in for a decision. The patterns here show up on pages about unrelated subjects, which suggests nobody chose them for the subject at hand. Each one is a heuristic: a reason to look closer and never a verdict on its own. Every pattern has legitimate uses, and the rule tables list the known false positives.

The common thread is decoration that imitates the signals of design without the content that earned them: photo-credit captions on stock images, `01 / INDEX` eyebrows, fake terminal windows built from `<div>`s, locale-and-weather strips. Ask what each element does for this product's content. An element with a content reason stays whatever the linter says, and an element without one goes whether or not the linter noticed it.

A single character is never evidence of how a page was produced. The punctuation and emoji rules below are editorial policy, and a finding from them says only that the text breaks the house style.

## Tier 1 - countable (enforced by the linter)

Run `python3 scripts/slop_check.py <path>` from the skill directory. The rules below are its default set, and [Handling findings](#handling-findings) says what FAIL and WARN require. Every rule is a literal pattern, so read each finding with these limits in mind:

- Rules scan source lines, including comments, strings, fixtures, and test data. They do not isolate rendered text, and a rule that needs a whole tag misses a tag split across lines.
- A match proves only that the literal occurs. Whether it is a defect depends on the brief, the product's system, and the rendered result.
- Line rules skip lines over 2,000 characters silently, while the per-file eyebrow and radius counts still read them. Files over 1,000,000 bytes are skipped with a `skipped-large` warning. Only `.jsx .tsx .js .ts .html .css .scss .svelte .vue .astro` files are read, and directory traversal skips `node_modules`, `.git`, `dist`, `build`, `.next`, and symlinked files.
- Some linter messages word a finding more strongly than the evidence supports, such as calling a dash the most reliable tell. This reference governs how a finding is read.

**House editorial policy.** `em-dash` and `emoji` enforce the skill's house style for UI text: no em dashes or en dashes, and no emoji. They are editorial policy rather than universal design guidance. Em dashes are standard punctuation and emoji can suit a brief, so a brief or product style guide that calls for them overrides the rule through a recorded exception.

| Rule | Severity | What it matches | Known false positives and limits |
|---|---|---|---|
| `em-dash` | FAIL | `U+2014` or `U+2013` anywhere on a line. | House editorial policy. Also fires in comments and on en dashes in numeric ranges. |
| `emoji` | FAIL | Any codepoint in `U+1F300` to `U+1FAFF`, `U+2600` to `U+27BF`, or `U+1F1E6` to `U+1F1FF`. | House editorial policy. The `U+2600` to `U+27BF` range includes check marks, crosses, and stars used as interface glyphs, and those fire too. |
| `banned-palette` | FAIL | One of 16 hex literals, case-insensitive. Cream and bone: `#f5f1ea`, `#f7f5f1`, `#fbf8f1`, `#efeae0`, `#ece6db`, `#faf7f1`, `#e8dfcb`. Brass, clay, and oxblood: `#b08947`, `#b6553a`, `#9a2436`, `#9c6e2a`, `#bc7c3a`, `#7d5621`. Espresso: `#1a1714`, `#1a1814`, `#1b1814`. | A match proves only that the literal occurs; it says nothing about how the color is used. The same color written as `rgb()`, `oklch()`, or eight-digit hex is missed. A brand guide that mandates one of these values is a recorded exception. |
| `h-screen` | FAIL | The `h-screen` class, which also matches inside `min-h-screen` and `max-h-screen`. | A viewport-height class is not always a mobile defect. It matters when content or controls at the bottom of the region can sit under mobile browser chrome, while a decorative full-bleed background or a `min-h-screen` wrapper often tolerates it. Check the bottom edge at a mobile width. |
| `scroll-listener` | FAIL | `addEventListener('scroll'` with single or double quotes. | A scroll listener is not proof of jank. A passive listener that batches work into `requestAnimationFrame` can be fine, and a performance trace while scrolling settles it. `onscroll` and backtick strings are missed. |
| `placeholder-comment` | FAIL | `//` followed by `...`, `rest of`, `implement`, `your code`, `add more`, `similar to`, or `continue`, case-insensitive, plus `/* ... */` and `{/* ... */}`. | Only these forms match. `// TODO`, HTML comments, and a bare ellipsis are not checked. An ordinary comment that starts with a listed word, such as `// implements the retry policy`, fires too. |
| `lorem-ipsum` | FAIL | `lorem ipsum`, case-insensitive. | Fires in fixtures and comments as well as UI text. |
| `stock-name` | FAIL | `John Doe`, `Jane Doe`, `Sarah Chan`, `Acme` (optionally `Inc` or `Corp`), `Cloudly`, or `SmartFlow`, case-sensitive. | A real customer or product with one of these names fires too. |
| `scroll-cue` | FAIL | `Scroll to explore`, `Scroll to discover`, or `Scroll down`, case-insensitive. The pattern also lists a down arrow (`U+2193`) before `scroll`, but that form matches only when a letter or digit directly precedes the arrow. | An arrow-only cue is effectively missed. The label of a real scroll control fires. |
| `eyebrow-budget` | FAIL | Per file, more eyebrows than `ceil(sections / 3)`. Sections are `<section` or `<Section` tags; eyebrows are class strings holding both `uppercase` and a `tracking` utility. | Per file only: it cannot see sections or labels in other components, so it cannot establish project or rendered consistency. It counts every uppercase tracked label, including navigation and table headers, and misses CSS `text-transform`. A file with no section tags is not checked. |
| `pure-black-white` | WARN | `#000`, `#000000`, `#fff`, or `#ffffff`. | Pure black or white that meets contrast and fits the direction is legitimate. `black`, `white`, and `rgb()` forms are missed. |
| `default-font` | WARN | A name containing `font-family` or `fontFamily`, custom properties included, whose first family is Inter, Roboto, Open Sans, Helvetica, or Arial. | The match cannot cross a comma, so a later family in the stack is missed, as are Tailwind `font-sans` and families set through variables. An existing system or a public-sector brief can call for these families. |
| `banned-font` | WARN | `Fraunces`, `Instrument Serif`, or `Playfair Display` (space or underscore), case-insensitive. | These are common display-serif defaults, and any of them can suit a brief. Any mention fires, including an import. |
| `lucide-icons` | WARN | `from 'lucide-react'` or its double-quoted form. | Acceptable when the project already depends on it. Subpath imports, other Lucide packages, and `require()` are missed. |
| `handrolled-icon` | WARN | An `<svg>` opening tag followed directly by `<path` or by the end of the line, unless it carries `aria-hidden="false"`. | Also fires on logos, illustrations, and charts. In a zero-dependency stack a consistent hand-rolled family is the icon system ([vanilla.md](vanilla.md#tells-that-invert-without-dependencies)). |
| `gradient-text` | WARN | `bg-clip-text` or `background-clip: text`. | Fires on any element, heading or otherwise, and on clipped fills that use no gradient. |
| `custom-cursor` | WARN | `cursor: url(`. | Review that the cursor keeps a visible hotspot and its usual meaning, and that a keyword fallback follows the URL. |
| `animate-layout-prop` | WARN | A `transition:` value naming `top`, `left`, `width`, or `height`, which includes `border-width` and `max-height`, or `animate` followed later on the same line by one of those names and a colon. | `transition-property` is missed, and an `animate-*` class beside an unrelated `height:` fires. A small, measured layout animation can be justified ([interaction.md](interaction.md#feedback-and-responsiveness)). |
| `flex-percent-math` | WARN | A Tailwind `w-[calc(...)]` value containing `%`. | A calculated width can be correct. Grid is the usual alternative for columns. |
| `middot-spam` | WARN | More than one middle dot (`U+00B7`) on a line. | A metadata row with three fields legitimately uses two separators. |
| `radius-scale` | WARN | Per file, more than two distinct radius numbers read from `rounded-[Npx]`, `rounded-[Nrem]`, and `border-radius: N`, after exempting 0, 50, 999, and 9999. | Extraction keeps only the leading integer. Units and fractional parts are dropped, so `8px` and `8rem` count as one value, `border-radius: 1.5rem` counts as 1, and `border-radius: 0.5rem` reads as 0 and is exempt. `rounded-[...]` with a fractional value is not matched, `50px` is exempt along with `50%`, and only the first value of a multi-value radius is read. Named utilities such as `rounded-lg`, per-corner properties, and variables are invisible. Per file only, so it cannot establish project or rendered consistency and is no audit of a token system. |
| `filler-verb` | WARN | `Elevate`, `Seamless`, `Seamlessly`, `Unleash`, `Next-Gen`, `Revolutionize`, `Game-changer`, `Gamechanger`, or `Delve` as whole words, case-insensitive. | Class names and tokens such as `elevate-1` fire too. |
| `fake-precision` | WARN | `99.99%`, `99.9%`, `100% uptime`, or `10x faster`. | A measured, sourced figure is legitimate; keep the source with it. |
| `performative-craft` | WARN | `Quietly in use at`, `Quietly trusted by`, `Field notes`, `From the field`, or `Currently on the bench`, case-insensitive. | `Field notes` can be a real section name. |
| `section-number-eyebrow` | WARN | Element text starting with `0` and a digit, then `/`, a middle dot, or a hyphen, then a word character. | Dates such as `03/14/2026` and real numbered steps fire too. |
| `hero-version-label` | WARN | Element text that is only a version such as `v1.2`, or `BETA`, `ALPHA`, `EARLY ACCESS`, `INVITE-ONLY`, or `INVITE ONLY`, case-insensitive. | It is not limited to the hero. Changelogs and release tables fire, and a real release stage can belong in the UI. |
| `placeholder-as-label` | WARN | An `<input>` tag on one line with `placeholder=` and neither `aria-label` nor `id=`. | An `id` is not proof of an associated label, and any attribute ending in `id=`, such as `data-testid`, suppresses the rule. An input inside a wrapping `<label>` fires, and `<textarea>` and tags split across lines are missed. Confirm the accessible name in the browser snapshot. |
| `skipped-large` | WARN | A file over 1,000,000 bytes. | Nothing in the file was inspected. Lint the source instead of the build. |
| `unreadable` | WARN | A file that could not be read. | Nothing in the file was inspected. |

## Craft checks

`python3 scripts/slop_check.py --craft <path>` runs the default rules plus five craft checks. All craft findings are WARN, because source text shows evidence and never the rendered result. Each message names the literal evidence and the review it asks for.

Declarations are read from `.css` files and from `<style>` blocks with no `lang` or `lang="css"` in `.html`, `.vue`, `.svelte`, and `.astro` files, with CSS comments and strings ignored and vendor prefixes removed. Class tokens are read from quoted `class` and `className` values in markup and script files. The checks do not inspect `.scss` files, other `<style lang>` blocks, inline `style` attributes, CSS-in-JS, `:class` bindings, expression or template-literal class names, variables, or the cascade; craft mode reports each skipped `.scss` file and `<style lang>` block as `scan-incomplete`, and the other gaps produce no finding.

- **`transition-all`.** Fires on a `transition` value that names `all`, a comma-separated item with a literal duration and no property name (which applies to all properties), a `transition-property` that includes `all`, or a class token whose final variant is `transition-all`, such as `hover:transition-all`. A value of `none` or a CSS-wide keyword is excluded, and an item without `all` that holds `var()`, `env()`, or `attr()` is skipped because a variable may supply the property. A broad transition can be intentional. Settle it by triggering each state change the rule covers under a browser performance trace, confirming which properties change and whether layout or paint runs, and then listing the properties meant to animate.
- **`long-transition`.** Fires when the first literal time in any comma-separated item of `transition` or `transition-duration` exceeds 500 ms, in `ms` or decimal `s`. The second time in a shorthand item is its delay and is ignored, a `var()` or `calc()` before the first time ends the scan of that item, and `animation` durations are out of scope. A narrative transition can justify the length. Settle it by reversing the state mid-transition in the browser and confirming that the element continues from its current position and accepts input throughout ([timing and easing](interaction.md#timing-and-easing)).
- **`infinite-animation`.** Fires on `infinite` in an `animation` or `animation-iteration-count` value. Utility classes such as `animate-spin` and animations started from script are not seen. A busy indicator or narrative media can justify the loop, and the declaration alone cannot show whether a pause, a static alternative, or a reduced-motion rule exists elsewhere. Settle it with the probe's `animations` check, run once normally and once under reduced-motion emulation ([reading probe output](finishing.md#reading-probe-output), [reduced motion](interaction.md#reduced-motion)).
- **`focus-outline-reset`.** Fires on `outline: none`, a zero-width `outline` or `outline-width`, or `outline-style: none` in a rule whose selector has `:focus` or `:focus-visible` outside any `:not(...)`, and on the `focus:outline-none`, `focus:outline-0`, `focus-visible:outline-none`, and `focus-visible:outline-0` tokens with an optional responsive prefix such as `md:`. A reset scoped by `:not(:focus-visible)` is exempt, and `:focus-within` does not count. The finding is suppressed when the same file has any replacement: in a `:focus` or `:focus-visible` rule, an outline with a positive literal or keyword width or any `box-shadow` other than `none` or a CSS-wide keyword, variables included; or a `focus:` or `focus-visible:` utility among `ring`, `ring-1`, `ring-2`, `ring-4`, and `ring-8`. That suppression is coarse. One replacement anywhere in the file silences every reset in it, including a reset on an unrelated control, which is a false negative, and a suppressed finding does not prove the replacement applies or has enough contrast. A replacement in another file does not count, so a component whose focus style lives in a global stylesheet still warns. A reset outside a focus selector, such as `button { outline: none }`, also removes the focus outline and is not detected. Settle it by pressing `Tab` to each affected control, reading the probe's `focus` check, capturing the focus state, and measuring `outlineColor` against the adjacent background at 3:1 ([the render loop](finishing.md#the-render-loop)).
- **`scan-incomplete`.** Reports that something was not inspected: an input with no UI files (line 0, with the supplied path), a file over 1,000,000 bytes (alongside `skipped-large`), an unreadable file (alongside `unreadable`), lines over 2,000 characters (reported once per file at the first skipped line with a count), a `.scss` file (line 0), or a `<style lang>` block other than CSS (at its opening line). It judges nothing about the UI. Settle it by covering the gap: lint the unminified source, point the linter at the right path, or review the skipped lines directly, and name whatever stays unchecked in the report. Only craft mode reports these gaps. The default run skips long lines without a finding and drops an input with no UI files, printing a note to stderr and exiting 0 only when no input has any.

## Handling findings

- **FAIL** blocks delivery until it is fixed, unless the brief overrides the rule. The report then records the retained exception as `rule: reason`, for example `banned-palette: the brand guide mandates #b08947 as the primary accent`. The run still exits 1 with a retained exception; the recorded exception in the report, not the exit code, is what clears the gate for that finding. An exception rests on the brief, a style guide, or the established system; preference alone does not qualify.
- **WARN** survives with a one-line reason in the report, such as `handrolled-icon: one 24-unit viewBox, 2px stroke, currentColor family in a zero-dependency build`. A warning with no reason gets fixed.
- **`--warn-only`** makes the run exit 0 and still prints every finding. The findings are recorded and remain unresolved: each FAIL in that output still needs a fix or a recorded exception.
- **`scan-incomplete`** means part of the input went uninspected. Complete that coverage by other means and name what remains unchecked; the gate has not passed for the uninspected part.
- **A clean lint is a floor.** It shows only that no listed pattern occurs in the lines that were inspected, and it is no evidence of visual quality. The judgment prompts below and the [render loop](finishing.md#the-render-loop) cover the rest.

## Tier 2 - judgment (human/agent review)

The linter cannot see these, and a clean lint says nothing about them. Judge each against the brief and the product's existing system, on the rendered result where one exists.

**Layout**
- A composition chosen by default instead of from the content: three identical feature cards for items that are not comparable, a centered hero the brief gives no reason for, or a run of alternating image-and-text rows that a list or table would carry better.
- Layout variation or repetition that ignores the content. A layout changes where the content changes kind and repeats where the content is comparable. Repeated layouts for comparable content, such as pricing tiers or product specifications, and an established documentation layout are consistency and survive review.
- A bento grid with an empty cell. N items means N cells.
- A primary action pushed below the first viewport at common widths when the brief makes that action the goal.

**Substance**
- Fake product UI built from `<div>`s: dashboards, terminals, or task lists that imitate a product without showing it. Use a real capture, a working demo, or nothing.
- An unfinished page presented as restraint. Text-only pages are legitimate for documentation, reference, legal, and reading surfaces. The tell is missing hierarchy, missing states, or content the brief promised and the page left out.
- Copy that performs thoughtfulness: forced metaphors, mock-humble asides, wordplay that bends the meaning. Plain, specific copy is the default.
- Motion with no stated purpose. If one sentence cannot say what an animation communicates ([what motion is for](interaction.md#what-motion-is-for)), remove it.
- Claimed motion that does not move. A page that promises "cinematic" and sits still is broken.

**Coherence**
- Consistency within the product: one token set for color, type, spacing, and radius, one icon family with one stroke width, and one corner-radius language, checked on captures across pages. The `radius-scale` and `eyebrow-budget` rules see one file at a time and cannot establish this.
- Variation only where content warrants it. A new accent, theme, palette, or display face marks a real difference in meaning, such as a dark code sample, a media viewer, or a status. Novelty between outputs is no reason to change a palette or typeface; the brief and the product's existing system decide ([direction first](foundations.md#direction-first)).
- These survive review: legitimate brand colors, including a banned-palette value a brand guide mandates; pure black or white that meets contrast; established documentation layouts; semantic status colors, which are roles of their own and never count as a second accent; and repeated layouts for comparable content.

## Rules deliberately NOT adopted

Recorded so each omission reads as a decision.

- **The "$200 tip / take a deep breath" prompt-boosting numbers.** The source repo cites `+45% quality`, `34%→80% accuracy`, and `+115% combined` to a "December 2025 controlled study", EmotionPrompt, and LazyBench, with no authors, DOIs, or URLs. They cannot be verified, and repeating them would dress unsourced numbers up as rigor.
- **Their exact dial defaults (`8 / 6 / 4`).** The dials are kept, but those specific defaults encode the source author's taste. The dials are inferred from the brief and the audience instead ([the three dials](foundations.md#the-three-dials)).
- **The serif blanket-discouragement.** "Creative brief means serif" is a real default worth naming, but the source overcorrects into near-prohibition. The three named display serifs stay flagged as WARN; serif as a category does not.
- **The two internal contradictions.** The source's `stitch-skill` recommends Fraunces and Instrument Serif, which `taste-skill` flags by name, and its `soft-skill` mandates eyebrow tags, which `taste-skill` caps at one per three sections. The skills were never reconciled because they ship separately. Both are resolved here in favor of the stricter rule and noted rather than silently picked.
