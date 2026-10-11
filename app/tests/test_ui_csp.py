"""SPEC-HARDENING-V1 H7: the UI carries no inline script, and its CSP says so.

The transcript renders agent-authored text, and on 2026-08-29 four separate
ways were found for that text to execute in the UI's origin - same-origin
with the API that seats agents, rewrites settings and deletes
conversations. Each was fixed at the sanitizer. H7 closes the class one
level lower: with no inline handler anywhere in `ui/`, `script-src` can
drop 'unsafe-inline', and the browser refuses injected script outright
rather than relying on a sanitizer catching every vector.

These are source-level guards. They are cheap, they run in the default
`uv run pytest`, and they fail where a contributor will see it - which is
the point, because the bug class is otherwise easy to reintroduce by
writing a new list row in the style of the old ones. No test drives a
browser, so nothing here proves the policy is actually ENFORCED; a typo in
it would leave the console just as quiet as a correct policy does.
"""

import re
from pathlib import Path

import pytest

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

# Matches an inline event-handler ATTRIBUTE (`onclick="..."`), not a
# property assignment (`eventSource.onerror = fn`), which is CSP-legal and
# is how this codebase wires the SSE stream. The `\b` and the quote are
# what separate the two.
# Matches an inline event-handler ATTRIBUTE in either HTML form - quoted
# (`onclick="x"`) or unquoted (`onclick=x`), because the unquoted form is
# valid HTML and would otherwise walk past a guard that demanded a quote.
# The lookbehind is what keeps `eventSource.onerror = fn` out: a property
# assignment is CSP-legal and is how this codebase wires the SSE stream.
INLINE_HANDLER = re.compile(r"""(?<![.\w])on[a-z]+\s*=\s*(?:["']|[A-Za-z_$])""")

# ui/lib/ is bundled third-party code (marked, highlight.js, mermaid),
# excluded because we do not author it. Whether those libraries inject an
# inline handler at RUNTIME is a browser question, and the e2e tier's
# console assertion is what answers it.
UI_SOURCES = sorted(
    p for p in UI_DIR.rglob("*")
    if p.suffix in {".js", ".html", ".css", ".svg"} and "lib" not in p.parts
)


def test_ui_sources_were_found():
    """Guard the guard: an empty file list would make every test below pass."""
    names = {p.name for p in UI_SOURCES}
    assert {"app.js", "index.html", "kb-graph-hud.js"} <= names, names


@pytest.mark.parametrize("path", UI_SOURCES, ids=lambda p: p.name)
def test_no_inline_event_handlers(path):
    hits = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if INLINE_HANDLER.search(line)
    ]
    assert not hits, (
        "inline event handler(s) found - use a data-action attribute and the "
        "CLICK_ACTIONS map in ui/app.js instead:\n" + "\n".join(hits)
    )


def _csp() -> str:
    html = (UI_DIR / "index.html").read_text()
    match = re.search(
        r"""http-equiv=["']Content-Security-Policy["']\s*"""
        r"""content=["'](.*?)["']\s*>""",
        html,
        re.DOTALL,
    )
    assert match, "no Content-Security-Policy meta tag in ui/index.html"
    return " ".join(match.group(1).split())


def _directive(name: str) -> str:
    for part in _csp().split(";"):
        part = part.strip()
        if part.split(" ")[0] == name:
            return part
    raise AssertionError(f"{name} missing from the CSP: {_csp()}")


def test_script_src_forbids_inline_and_eval():
    """The payoff for the handler removal, and the reason it was worth doing."""
    script_src = _directive("script-src")
    assert "'unsafe-inline'" not in script_src, script_src
    assert "'unsafe-eval'" not in script_src, script_src
    assert "'self'" in script_src, script_src


def test_style_src_keeps_unsafe_inline_deliberately():
    """Not an oversight: the bundled libraries emit inline styles, this UI has
    no build step to hash them, and style is not the half that executes.
    Pinned so a later tightening is a decision rather than an accident."""
    assert "'unsafe-inline'" in _directive("style-src")


@pytest.mark.parametrize(
    "directive, expected",
    [
        ("default-src", "'self'"),
        ("connect-src", "'self'"),   # closes the beacon class
        ("object-src", "'none'"),
        ("base-uri", "'none'"),      # stops a <base> tag rewriting script URLs
        ("frame-src", "'none'"),
        ("form-action", "'none'"),
    ],
)
def test_supporting_directives_hold(directive, expected):
    assert _directive(directive) == f"{directive} {expected}"


def test_every_data_action_has_a_handler():
    """A data-action naming an entry the map does not have is a dead control:
    silent, no console error, no CSP violation. Cross-check the two sides."""
    used = set()
    for path in UI_SOURCES:
        used |= set(re.findall(r"""data-action=["']([a-z-]+)["']""",
                               path.read_text()))
    app_js = (UI_DIR / "app.js").read_text()
    block = re.search(r"const CLICK_ACTIONS = \{(.*?)\n\};", app_js, re.DOTALL)
    assert block, "CLICK_ACTIONS map not found in ui/app.js"
    defined = set(re.findall(r"""^\s*['"]([a-z-]+)['"]:""",
                             block.group(1), re.MULTILINE))
    assert used <= defined, f"data-action with no handler: {used - defined}"
    assert defined <= used, f"handler no markup uses: {defined - used}"
