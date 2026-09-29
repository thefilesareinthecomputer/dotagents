# Walkthrough examples

Builds of the walkthrough brief in `../../evals/files/walkthrough/content.md`, kept in order so any two can be opened side by side to show what changed.
Each new build that the user signs off is saved as the next number; earlier files are never edited or removed.

| File | Status | How it was made |
|---|---|---|
| `01-rejected-old-skill.html` | Rejected | A fresh builder following the original skill. |
| `02-rejected-new-skill.html` | Rejected | A fresh builder following the first rewrite, before its art-direction teaching. Every lint and probe check passed; the page was still generic. |
| `03-approved-floor.html` | Approved floor | Hand-built and refined in review. The lowest approved aesthetic standard for this brief. |

The approved floor is the bar for the behavior eval: a build that falls below it fails, whatever its lint and probe results say.
It earns that place through a full-viewport hero with display-scale type and one spatial light composition, a warm paper editorial body with a distinct dark stage for the peak, and a pinned, scroll-scrubbed reading whose frame stays still while only the band, curve, and cursor move.
Study the floor's level of commitment without copying its choices; a build for the same brief must not reuse its composition.

Serve this directory over `http://127.0.0.1` to view the pages; they load their fonts from Google Fonts.
