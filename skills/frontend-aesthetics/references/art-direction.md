# Art direction

Choose what the visitor should remember, then make the composition give that event priority. The brief and existing design system govern these decisions; an operational screen can express its direction through task hierarchy.

**Contents**

- [Allocate emphasis](#allocate-emphasis)
- [Reject unearned defaults](#reject-unearned-defaults)
- [Carry one subject](#carry-one-subject)
- [Worked walkthrough](#worked-walkthrough)

## Allocate emphasis

Name one memorable product event before choosing tokens: the sample becomes a reading, the assembly locks together, or the comparison explains a decision. Locate that peak in the story. It may belong in the hero or a later scene.

Sketch the hero, one middle section, and the peak together. Give the peak the strongest combined scale, contrast, color, and motion. Supporting sections can vary, but two equally emphatic events compete for recall. Build the hero and peak before repeating sections, and compare their captures at thumbnail size. If a decorative element attracts attention first, reduce its size, saturation, contrast, or movement, or remove it.

For each section, write its narrative job and the composition that serves it. An introduction can use a large object crop; an operation can pair a narrow copy rail with a wide figure; a transformation can occupy a bounded stage; a result can settle into aligned rows. Keep a shared grid and type system while changing spatial relationships with the story. Repetition belongs where the content is comparable.

Give empty space a specific job, such as separating cause from result, preserving an object's silhouette, or directing attention toward an aperture. Space without that relationship needs recomposition. Spending more space on a tiny drawing does not make the drawing dominant.

## Reject unearned defaults

Check the proposed build for these patterns before implementation. Reject them when they lack a reason in the brief or established product system; they guide review without making claims about model internals. The inverse of each row (a paper canvas, a large serif, a dark stage, a scroll pin) is equally an unearned default when nothing in the brief asks for it.

| Pattern to check | Concrete decision to make |
|---|---|
| A dark canvas with one warm accent covers the whole page. | Assign color to the subject and narrative roles. Reserve a meaningful color change for the peak instead of tinting every section alike. |
| System fonts and a small headline carry an expressive launch brief. | Choose a real display face for its letterforms and test it at display scale. For example, expressive launch headlines often land around 96-160px on a roomy desktop, budgeted against viewport height, line count, copy, and actions. Keep required system fonts in established application UI. |
| A symmetric, half-empty hero gives copy and a small drawing equal columns. | Allocate space by priority. Enlarge or crop the subject, change the column ratio, or give artwork a separate row that it visibly occupies. |
| Three-card rows or alternating left/right zigzags organize unlike steps. | Compose each operation, transformation, comparison, and result according to its reading task. |
| Decorative loops, count-ups, and glow appear throughout. | Name the information each effect communicates and where it stops. Remove effects that compete with the peak or obscure the final value. Keep a loop or count-up only when its behavior serves the brief and remains controllable and accessible. |

Use optical sizing when the face provides it, inspect actual glyphs and fallback wrapping, and protect ascenders and descenders inside reveal masks. More effects cannot compensate for weak scale or an indistinct subject. A premium result needs deliberate proportions, credible material, and finished states as well as clean alignment.

## Carry one subject

Carry one identifiable specimen, object, or record through the page. A measured sample should produce the same curve in the reading, comparison, and saved entry. Label illustrative data and simulated outcomes. A working illustrative control must support keyboard and touch; otherwise make its noninteractive status clear.

Establish the object's proportions, aperture, seam, button, and light direction before drawing additional views. Reuse SVG symbols or shared geometry where practical. Compare a contact sheet of all views: perspective can change, but component placement and proportions must describe the same object. Preserve a distinctive mark on the specimen so continuity survives a crop.

Add material through specific geometry: a thin rim highlight, a darker sidewall, a narrow seam, or a contact shadow at the supporting surface. Keep lighting consistent across scenes. Inspect the silhouette at narrow widths before adding grain, bloom, or blur. Coupled graphics share the coordinate system described in [layered compositions](foundations.md#layered-compositions).

## Worked walkthrough

**Brief.** Present a handheld instrument through aiming at a leaf, capturing a sample, revealing a reading, comparing references, and saving a notebook entry.

**Generic build.** A small system-font headline sits beside a narrow instrument drawing in a half-empty graphite hero. Amber accents and glows repeat through symmetric sections. Alternating rows redraw the device with different proportions, while floating objects and counting specifications keep moving. The reading receives the same scale and contrast as everything else, so the visitor cannot identify the story's peak even when contrast and overflow checks pass.

**Premium build.** A large display headline and close instrument crop establish the physical subject. For this brief, Newsreader at roughly 120px on a roomy desktop and a clearly drawn aperture could provide that identity. The same notched leaf and instrument continue through quieter aiming and capture scenes. A later full-width reading stage gets the strongest color transformation and sustained motion; the hero hints at measurement without duplicating that transformation. Warm paper result sections let the exact same curve carry into comparison and the notebook. A rim, seam, and grounded shadow explain the material without surrounding every object with glow.

The cuts follow the allocation: remove competing motion and duplicated spectacle, preserve effects that explain the operation, and keep final specifications immediately readable. Another brief could make the hero the peak or justify ambient motion or changing numbers. Copy the method of assigning emphasis and checking continuity; choose fonts, surfaces, effects, and the peak from the new subject.
