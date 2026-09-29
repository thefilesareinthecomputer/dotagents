#!/usr/bin/env python3
"""Test the opt-in --craft checks in slop_check.py with stdlib unittest.

    python3 -B -m unittest discover -s skills/frontend-aesthetics/tests

Each craft rule gets matches, legitimate near misses, boundary cases, and a CLI
case. Legacy behavior without --craft stays locked by test_cli_contract.py.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "slop_check.py"
FIXTURES = ROOT / "tests" / "fixtures"
SPEC = importlib.util.spec_from_file_location("slop_check_under_craft_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
slop_check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = slop_check  # dataclasses look the module up by name
SPEC.loader.exec_module(slop_check)

CRAFT_RULES = {
    "transition-all", "long-transition", "infinite-animation", "focus-outline-reset", "scan-incomplete",
}
LOOKED_FOR = "(looked for: .astro .css .html .js .jsx .scss .svelte .ts .tsx .vue)"
# Words that would assert a rendered defect the source cannot show.
VERDICT_WORDS = ("fails", "failure", "violat", "inaccessible", "broken", "invisible")


def run(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *[str(arg) for arg in args]],
        capture_output=True,
        text=True,
        timeout=30,
    )


def write(root: Path, name: str, content: str | bytes) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return path


def craft(content: str | bytes, name: str = "case.css") -> list[tuple[str, int]]:
    """(rule, line) for each craft finding in one temporary file."""
    with tempfile.TemporaryDirectory() as tmp:
        path = write(Path(tmp), name, content)
        return [(f.rule, f.line) for f in slop_check.check_file(path, craft=True) if f.rule in CRAFT_RULES]


def craft_messages(content: str, name: str = "case.css") -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = write(Path(tmp), name, content)
        return [f.message for f in slop_check.check_file(path, craft=True) if f.rule in CRAFT_RULES]


class CaseTable(unittest.TestCase):
    def check_cases(self, cases: tuple[tuple[str, str, str, list[tuple[str, int]]], ...]) -> None:
        for label, name, content, expected in cases:
            with self.subTest(case=label):
                self.assertEqual(craft(content, name), expected)


class TestTransitionAll(CaseTable):
    def test_matches(self) -> None:
        rule = "transition-all"
        self.check_cases((
            ("names all", "a.css", ".a { transition: all 200ms ease; }", [(rule, 1)]),
            ("omitted property", "a.css", ".a { transition: 200ms ease; }", [(rule, 1)]),
            ("transition-property", "a.css", ".a { transition-property: opacity, all; }", [(rule, 1)]),
            ("literal utility", "a.tsx", '<div className="px-2 transition-all duration-200" />', [(rule, 1)]),
            ("utility with variant", "a.html", '<div class="md:transition-all">x</div>', [(rule, 1)]),
        ))

    def test_near_misses(self) -> None:
        self.check_cases((
            ("named property", "a.css", ".a { transition: opacity 200ms ease; }", []),
            ("none", "a.css", ".a { transition: none; }", []),
            ("none important", "a.css", ".a { transition: none !important; }", []),
            ("inherit", "a.css", ".a { transition: inherit; }", []),
            ("initial", "a.css", ".a { transition: initial; }", []),
            ("unset", "a.css", ".a { transition: unset; }", []),
            ("revert", "a.css", ".a { transition: revert; }", []),
            ("revert-layer", "a.css", ".a { transition: revert-layer; }", []),
            ("property list", "a.css", ".a { transition-property: opacity, transform; }", []),
            ("other utilities", "a.tsx", '<div className="transition-colors transition-opacity" />', []),
            ("comment", "a.css", "/* .a { transition: all 1s; } */\n.b { color: red; }", []),
            ("string", "a.css", '.a::after { content: "transition: all 1s"; }', []),
            ("variable", "a.css", ".a { transition: var(--motion-standard); }", []),
            ("vue binding", "a.vue", "<template><p :class=\"{ 'transition-all': on }\">x</p></template>", []),
            ("scss is not parsed", "a.scss", ".a { transition: all 1s; }", [("scan-incomplete", 0)]),
        ))

    def test_boundaries(self) -> None:
        rule = "transition-all"
        self.check_cases((
            ("easing without duration", "a.css", ".a { transition: ease; }", []),
            ("second item omits property", "a.css", ".a { transition: opacity 200ms, 300ms; }", [(rule, 1)]),
            ("uppercase", "a.css", ".a { TRANSITION: ALL 200MS; }", [(rule, 1)]),
            ("all with variable duration", "a.css", ".a { transition: all var(--duration); }", [(rule, 1)]),
            ("vendor prefix", "a.css", ".a { -webkit-transition: all 200ms; }", [(rule, 1)]),
            ("multiline declaration", "a.css",
             ".a {\n  transition:\n    opacity 200ms,\n    all 300ms;\n}", [(rule, 2)]),
            ("multiline class value", "a.html",
             '<div\n  class="px-2\n    transition-all">x</div>', [(rule, 3)]),
        ))


class TestLongTransition(CaseTable):
    def test_matches(self) -> None:
        rule = "long-transition"
        self.check_cases((
            ("shorthand", "a.css", ".a { transition: opacity 800ms ease; }", [(rule, 1)]),
            ("longhand list", "a.css", ".a { transition-duration: 200ms, 0.8s; }", [(rule, 1)]),
            ("bezier commas", "a.css",
             ".a { transition: opacity 200ms cubic-bezier(0.2, 0, 0, 1), transform 800ms ease; }", [(rule, 1)]),
        ))

    def test_near_misses(self) -> None:
        self.check_cases((
            ("long delay, short duration", "a.css", ".a { transition: opacity 200ms 900ms; }", []),
            ("delay after easing", "a.css", ".a { transition: opacity 200ms ease-out 2s; }", []),
            ("steps commas", "a.css",
             ".a { transition: opacity 200ms steps(4, end), transform 300ms linear; }", []),
            ("variable duration", "a.css", ".a { transition: opacity var(--duration-slow); }", []),
            ("variable longhand", "a.css", ".a { transition-duration: var(--duration-slow); }", []),
            ("variable before time", "a.css", ".a { transition: opacity var(--duration) 800ms; }", []),
            ("calc is not resolved", "a.css", ".a { transition: opacity calc(1s * 2); }", []),
            ("animation durations are exempt", "a.css", ".a { animation: fade 2s ease; }", []),
            ("comment", "a.css", "/* .a { transition: opacity 5s; } */", []),
            ("string", "a.css", '.a::after { content: "transition: opacity 5s"; }', []),
        ))

    def test_boundaries(self) -> None:
        rule = "long-transition"
        for duration, expected in (("500ms", []), ("0.5s", []), (".5s", []), ("501ms", [(rule, 1)]),
                                   ("0.51s", [(rule, 1)]), ("0.501s", [(rule, 1)]), ("500.1ms", [(rule, 1)])):
            for css in (f".a {{ transition: opacity {duration} ease; }}",
                        f".a {{ transition-duration: {duration}; }}"):
                with self.subTest(css=css):
                    self.assertEqual(craft(css), expected)
        self.assertEqual(
            craft(".a {\n  transition:\n    opacity 200ms,\n    transform 800ms;\n}"), [(rule, 2)])


class TestInfiniteAnimation(CaseTable):
    def test_matches(self) -> None:
        rule = "infinite-animation"
        self.check_cases((
            ("spinner shorthand", "a.css", ".spinner { animation: spin 1s linear infinite; }", [(rule, 1)]),
            ("iteration count", "a.css", ".a { animation-iteration-count: infinite; }", [(rule, 1)]),
            ("count list", "a.css", ".a { animation-iteration-count: 1, infinite; }", [(rule, 1)]),
        ))

    def test_spinner_message_requests_review_without_a_verdict(self) -> None:
        [message] = craft_messages(".spinner { animation: spin 1s linear infinite; }")
        self.assertIn('"spin 1s linear infinite"', message)
        self.assertIn("review", message)
        self.assertIn("reduced-motion", message)
        for word in VERDICT_WORDS:
            self.assertNotIn(word, message.lower())

    def test_near_misses(self) -> None:
        self.check_cases((
            ("name contains infinite", "a.css", ".a { animation: infinite-scroll 20s linear; }", []),
            ("finite count", "a.css", ".a { animation: spin 1s linear 3; }", []),
            ("animation-name", "a.css", ".a { animation-name: infinite; }", []),
            ("variable count", "a.css", ".a { animation: spin 1s var(--repeat); }", []),
            ("comment", "a.css", "/* .a { animation: spin 1s infinite; } */", []),
            ("string", "a.css", '.a::after { content: "animation: spin 1s infinite"; }', []),
        ))

    def test_boundaries(self) -> None:
        rule = "infinite-animation"
        self.check_cases((
            ("uppercase", "a.css", ".a { animation: spin 1s INFINITE; }", [(rule, 1)]),
            ("second of two animations", "a.css",
             ".a {\n  animation:\n    fade 1s,\n    spin 1s linear infinite;\n}", [(rule, 2)]),
            ("vendor prefix", "a.css", ".a { -webkit-animation: spin 1s infinite; }", [(rule, 1)]),
        ))


class TestFocusOutlineReset(CaseTable):
    VISIBLE_OUTLINE = ".a:focus-visible { outline: 2px solid var(--color-focus); }"

    def test_matches(self) -> None:
        rule = "focus-outline-reset"
        self.check_cases((
            ("focus reset, no replacement", "a.css", ".a:focus { outline: none; }", [(rule, 1)]),
            ("zero width", "a.css", ".a:focus { outline: 0; }", [(rule, 1)]),
            ("focus-visible reset", "a.css", ".a:focus-visible { outline: none; }", [(rule, 1)]),
            ("outline-style", "a.css", ".a:focus { outline-style: none; }", [(rule, 1)]),
            ("outline-width", "a.css", ".a:focus { outline-width: 0px; }", [(rule, 1)]),
            ("utility", "a.html", '<a class="focus:outline-none" href="/">x</a>', [(rule, 1)]),
            ("responsive utility", "a.tsx", '<a className="md:focus:outline-none" href="/">x</a>', [(rule, 1)]),
            ("focus-visible utility", "a.tsx", '<a className="lg:focus-visible:outline-0" />', [(rule, 1)]),
        ))

    def test_message_names_evidence_and_requests_verification(self) -> None:
        [message] = craft_messages(".a:focus { outline: none; }")
        self.assertIn('"outline: none" in a :focus rule', message)
        self.assertIn("no :focus or :focus-visible", message)
        self.assertTrue(message.endswith("verify the rendered focus indicator"))
        for word in VERDICT_WORDS:
            self.assertNotIn(word, message.lower())
        [message] = craft_messages(".a:focus:not(:focus-visible), .b:focus-visible { outline: none; }")
        self.assertIn('"outline: none" in a :focus-visible rule', message)

    def test_near_misses(self) -> None:
        reset = ".a:focus { outline: none; }\n"
        self.check_cases((
            ("base reset outside a focus rule", "a.css", ".a { outline: none; }", []),
            ("focus-within is not focus", "a.css", ".menu:focus-within { outline: none; }", []),
            ("escaped utility selector", "a.css", ".md\\:focus\\:outline-none:hover { outline: none; }", []),
            ("focus-visible outline", "a.css", reset + self.VISIBLE_OUTLINE, []),
            ("focus-visible outline-width", "a.css", reset + ".a:focus-visible { outline-width: thin; }", []),
            ("focus-visible box-shadow", "a.css",
             reset + ".a:focus-visible { box-shadow: 0 0 0 3px var(--color-focus); }", []),
            ("box-shadow variable only", "a.css", reset + ".a:focus-visible { box-shadow: var(--ring); }", []),
            ("focus box-shadow variable only", "a.css", reset + ".a:focus { box-shadow: var(--focus-ring); }", []),
            ("ring utility", "a.html", '<a class="focus:outline-none focus-visible:ring" href="/">x</a>', []),
            ("ring-2 utility", "a.tsx", '<a className="focus:outline-none focus-visible:ring-2" />', []),
            ("style block reset, markup ring replacement", "a.html",
             '<style>.a:focus { outline: none; }</style>\n<a class="focus-visible:ring-2">x</a>', []),
            ("focus box-shadow in the resetting rule", "a.css",
             ".a:focus { outline: none; box-shadow: 0 0 0 3px #1d4ed8; }", []),
            ("focus outline replacement", "a.css", reset + ".b:focus { outline: 2px solid #1d4ed8; }", []),
            ("focus outline-width replacement", "a.css", reset + ".b:focus { outline-width: thick; }", []),
            ("focus ring utility", "a.html", '<a class="focus:outline-none focus:ring" href="/">x</a>', []),
            ("focus ring-2 utility, Tailwind v3 form", "a.tsx",
             '<input className="focus:outline-none focus:ring-2" />', []),
            ("responsive focus ring utility", "a.tsx", '<a className="focus:outline-none md:focus:ring-4" />', []),
            ("mouse-only focus reset", "a.css", ".a:focus:not(:focus-visible) { outline: none; }", []),
            ("not focus-visible reset", "a.css", ".a:not(:focus-visible) { outline: 0; }", []),
            ("focus only inside :not()", "a.css", ".a:not(:focus) { outline: none; }", []),
            ("focus inside nested :not()", "a.css", ".a:not(:is(.b:focus)) { outline: none; }", []),
            ("comma inside :not() stays in one member", "a.css",
             ".a:focus:not(.b, :focus-visible) { outline: none; }", []),
            ("replacement in one list member", "a.css",
             reset + ".x:hover, .a:focus-visible { box-shadow: 0 0 0 2px #000; }", []),
            ("comma and focus inside a selector string", "a.css", '.a[title="x, .b:focus"] { outline: none; }', []),
        ))
        for size in ("1", "2", "4", "8"):
            with self.subTest(focus_ring=size):
                self.assertEqual(craft(f'<a className="focus:outline-none focus:ring-{size}" />', "a.tsx"), [])

    def test_boundaries(self) -> None:
        rule = "focus-outline-reset"
        utility = '<a className="focus:outline-none {extra}" />'
        self.check_cases((
            ("ring-0 does not replace", "a.tsx", utility.format(extra="focus-visible:ring-0"), [(rule, 1)]),
            ("ring color does not replace", "a.tsx",
             utility.format(extra="focus-visible:ring-blue-500"), [(rule, 1)]),
            ("focus ring-0 does not replace", "a.tsx", utility.format(extra="focus:ring-0"), [(rule, 1)]),
            ("focus ring color does not replace", "a.tsx", utility.format(extra="focus:ring-blue-500"), [(rule, 1)]),
            ("focus-within ring is not focus", "a.tsx", utility.format(extra="focus-within:ring-2"), [(rule, 1)]),
            ("focus-within box-shadow is not focus", "a.css",
             ".a:focus { outline: none; }\n.menu:focus-within { box-shadow: 0 0 0 3px blue; }", [(rule, 1)]),
            ("focus box-shadow none", "a.css", ".a:focus { outline: none; box-shadow: none; }", [(rule, 1)]),
            ("box-shadow CSS-wide keyword", "a.css", ".a:focus { outline: none; box-shadow: inherit; }", [(rule, 1)]),
            ("focus outline reset does not replace", "a.css",
             ".a:focus { outline: none; }\n.b:focus { outline-width: 0; }", [(rule, 1), (rule, 2)]),
            ("focus replacement outside a focus rule", "a.css",
             ".a:focus { outline: none; }\n.a:hover { box-shadow: 0 0 0 3px blue; }", [(rule, 1)]),
            ("other :not() is still a reset", "a.css", ".a:focus:not(.b) { outline: none; }", [(rule, 1)]),
            ("focus-visible after :not() is still a reset", "a.css",
             ".a:not(:hover):focus-visible { outline: none; }", [(rule, 1)]),
            ("focus after nested :not() is still a reset", "a.css",
             ".a:is(:not(.x)):focus { outline: none; }", [(rule, 1)]),
            ("list member outside :not(:focus-visible) resets", "a.css",
             ".a:focus:not(:focus-visible), .b:focus { outline: none; }", [(rule, 1)]),
            ("comma inside :is() stays in one member", "a.css", ".a:is(.b, .c):focus { outline: none; }", [(rule, 1)]),
            ("box-shadow scoped away from focus does not replace", "a.css",
             ".a:focus { outline: none; }\n.a:not(:focus-visible) { box-shadow: 0 0 0 2px #000; }", [(rule, 1)]),
            ("commented-out replacement", "a.css",
             ".a:focus { outline: none; }\n/* .a:focus-visible { outline: 2px solid blue; } */", [(rule, 1)]),
            ("replacement inside a string", "a.css",
             '.a:focus { outline: none; }\n.b::after { content: ".a:focus-visible { outline: 2px solid }"; }',
             [(rule, 1)]),
            ("box-shadow none", "a.css",
             ".a:focus { outline: none; }\n.a:focus-visible { box-shadow: none; }", [(rule, 1)]),
            ("outline without literal width", "a.css",
             ".a:focus { outline: none; }\n.a:focus-visible { outline: var(--focus-outline); }", [(rule, 1)]),
            ("focus outline without literal width", "a.css",
             ".a:focus { outline: none; }\n.a:focus { outline: var(--focus-outline); }", [(rule, 1)]),
            ("multiline rule", "a.css",
             ".a,\n.b:focus {\n  color: red;\n  outline:\n    none;\n}", [(rule, 4)]),
            ("inside a media query", "a.css",
             "@media (min-width: 40em) {\n  .a:focus { outline: none; }\n}", [(rule, 2)]),
        ))

    def test_unrelated_focus_visible_rule_still_suppresses(self) -> None:
        # Documented false-negative limit: suppression is file-wide and does not
        # check that the replacement applies to the control that lost its outline.
        css = ".a:focus { outline: none; }\n.unrelated:focus-visible { outline: 2px solid blue; }"
        self.assertEqual(craft(css), [])
        markup = '<a class="focus:outline-none">x</a>\n<b class="focus-visible:ring-2">y</b>'
        self.assertEqual(craft(markup, "a.html"), [])


class TestComponentStyleBlocks(unittest.TestCase):
    EXPECTED = [
        ("transition-all", 3),
        ("focus-outline-reset", 4),
        ("focus-outline-reset", 19),
        ("infinite-animation", 23),
        ("scan-incomplete", 27),
    ]

    def test_fixture_lines_match_the_whole_file(self) -> None:
        content = (FIXTURES / "craft_component.vue").read_text(encoding="utf-8")
        self.assertEqual(craft(content, "c.vue"), self.EXPECTED)
        # CRLF line endings keep the same numbering.
        self.assertEqual(craft(content.replace("\n", "\r\n"), "c.vue"), self.EXPECTED)

    def test_every_component_suffix_reads_style_blocks(self) -> None:
        content = "<p>Menu</p>\n\n<style>\n.a { transition: all 200ms; }\n</style>\n"
        for suffix in (".html", ".vue", ".svelte", ".astro"):
            with self.subTest(suffix=suffix):
                self.assertEqual(craft(content, "c" + suffix), [("transition-all", 4)])

    def test_script_files_only_contribute_class_utilities(self) -> None:
        content = "const css = `<style>.a { transition: all 1s; }</style>`;\n"
        self.assertEqual(craft(content, "c.tsx"), [])

    def test_unclosed_style_block_runs_to_end_of_file(self) -> None:
        self.assertEqual(craft("<style>\n.a:focus {\n  outline: none;\n", "c.svelte"),
                         [("focus-outline-reset", 3)])


class TestScanIncomplete(unittest.TestCase):
    def test_long_lines_are_aggregated_once_per_file(self) -> None:
        content = ".a { color: red; }\n" + "x" * 2_001 + "\n" + "y" * 5_000 + "\n"
        self.assertEqual(craft(content), [("scan-incomplete", 2)])
        [message] = craft_messages(content)
        self.assertIn("2 line(s) over 2000 characters", message)
        self.assertIn("starting at line 2", message)

    def test_line_cap_boundary(self) -> None:
        for size, expected in ((2_000, []), (2_001, [("scan-incomplete", 1)])):
            with self.subTest(size=size):
                self.assertEqual(craft("x" * size + "\n", "a.tsx"), expected)

    def test_skipped_line_hides_its_declarations(self) -> None:
        line = ".a:focus {" + " " * 2_000 + "outline: none; }"
        self.assertEqual(craft(line + "\n"), [("scan-incomplete", 1)])

    def test_size_cap_adds_coverage_after_skipped_large(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), "large.css", b"x" * 1_000_001)
            report = json.loads(run("--craft", "--json", path).stdout)
            self.assertEqual([(f["rule"], f["severity"], f["line"]) for f in report["findings"]],
                             [("skipped-large", "WARN", 0), ("scan-incomplete", "WARN", 0)])
            self.assertEqual(report["files"], 1)
            legacy = json.loads(run("--json", path).stdout)
            self.assertEqual([f["rule"] for f in legacy["findings"]], ["skipped-large"])

    SCSS_MESSAGE = ("SCSS is not parsed for craft declarations in this file; "
                    "review transitions, animations, and focus styles by other means")
    SCSS = ".a { transition: all 1s; }\n.b:focus { outline: none; }\n.c { animation: spin 1s infinite; }\n"
    VUE = ("<template><p>x</p></template>\n<style>\n.a { transition: all 200ms; }\n</style>\n"
           '<style scoped lang="scss">\n.b { transition: all 1s; }\n</style>\n')

    def test_scss_file_is_reported_once(self) -> None:
        self.assertEqual(craft(self.SCSS, "a.scss"), [("scan-incomplete", 0)])
        self.assertEqual(craft_messages(self.SCSS, "a.scss"), [self.SCSS_MESSAGE])

    def test_non_css_style_block_is_reported_at_its_opening_line(self) -> None:
        self.assertEqual(craft(self.VUE, "c.vue"), [("transition-all", 3), ("scan-incomplete", 5)])
        self.assertEqual(craft_messages(self.VUE, "c.vue")[1],
                         '<style scoped lang="scss"> block is not parsed for craft declarations; '
                         "review transitions, animations, and focus styles by other means")
        for lang in ("scss", "less", "postcss", "SCSS"):
            with self.subTest(lang=lang):
                content = f"<p>x</p>\n<style\n  lang='{lang}'\n>\n.a {{ transition: all 1s; }}\n</style>\n"
                self.assertEqual(craft(content, "c.svelte"), [("scan-incomplete", 2)])
        for tag in ("<style>", '<style lang="css">', "<style lang=CSS>"):
            with self.subTest(tag=tag):
                self.assertEqual(craft(f"<p>x</p>\n{tag}\n.a {{ color: red; }}\n</style>\n", "c.astro"), [])

    def test_skipped_style_regions_in_json_and_legacy(self) -> None:
        fields = {"path": str, "line": int, "severity": str, "rule": str, "message": str}
        with tempfile.TemporaryDirectory() as tmp:
            for name, content, expected in (("a.scss", self.SCSS, [("scan-incomplete", 0)]),
                                            ("c.vue", self.VUE, [("transition-all", 3), ("scan-incomplete", 5)])):
                with self.subTest(name=name):
                    path = write(Path(tmp), name, content)
                    proc = run("--craft", "--json", path)
                    self.assertEqual((proc.returncode, proc.stderr), (0, ""))
                    report = json.loads(proc.stdout)
                    self.assertEqual(set(report), {"findings", "files"})
                    self.assertEqual(report["files"], 1)
                    self.assertEqual([(f["rule"], f["line"]) for f in report["findings"]], expected)
                    for finding in report["findings"]:
                        self.assertEqual({key: type(value) for key, value in finding.items()}, fields)
                        self.assertEqual((finding["path"], finding["severity"]), (str(path), "WARN"))
                    self.assertEqual(json.loads(run("--json", path).stdout), {"findings": [], "files": 1})
                    legacy = run(path)
                    self.assertEqual((legacy.returncode, legacy.stderr), (0, ""))
                    self.assertNotIn("scan-incomplete", legacy.stdout)

    def test_read_error_adds_coverage_after_unreadable(self) -> None:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("Root can read files regardless of their permission bits")
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), "locked.css", ".a { color: red; }\n")
            original_mode = path.stat().st_mode
            try:
                path.chmod(0)
                try:
                    path.read_bytes()
                except PermissionError:
                    pass
                else:
                    self.skipTest("The platform still permits reading a mode-0 file")
                proc = run("--craft", "--json", path)
                self.assertEqual(proc.returncode, 0)
                report = json.loads(proc.stdout)
                self.assertEqual([(f["rule"], f["line"]) for f in report["findings"]],
                                 [("unreadable", 0), ("scan-incomplete", 0)])
            finally:
                path.chmod(original_mode)


class TestCraftCLI(unittest.TestCase):
    RULE_CASES = (
        ("transition-all", "a.css", ".a { transition: all 200ms; }\n", 1),
        ("long-transition", "a.css", ".a {\n  transition: opacity 900ms;\n}\n", 2),
        ("infinite-animation", "a.vue", "<p>x</p>\n<style>\n.a { animation: spin 1s infinite; }\n</style>\n", 3),
        ("focus-outline-reset", "a.tsx", '<a className="focus:outline-none" href="/">x</a>\n', 1),
        ("scan-incomplete", "a.tsx", "<p>x</p>\n" + "z" * 2_001 + "\n", 2),
    )

    def test_each_rule_in_json_and_text(self) -> None:
        fields = {"path": str, "line": int, "severity": str, "rule": str, "message": str}
        with tempfile.TemporaryDirectory() as tmp:
            for rule, name, content, line in self.RULE_CASES:
                with self.subTest(rule=rule):
                    path = write(Path(tmp), name, content)
                    proc = run("--craft", "--json", path)
                    self.assertEqual((proc.returncode, proc.stderr), (0, ""))
                    report = json.loads(proc.stdout)
                    self.assertEqual(set(report), {"findings", "files"})
                    self.assertEqual(report["files"], 1)
                    self.assertEqual([(f["rule"], f["severity"], f["line"]) for f in report["findings"]],
                                     [(rule, "WARN", line)])
                    finding = report["findings"][0]
                    self.assertEqual({key: type(value) for key, value in finding.items()}, fields)
                    self.assertEqual(finding["path"], str(path))
                    self.assertFalse({chr(0x2013), chr(0x2014)} & set(finding["message"]))
                    text = run("--craft", path)
                    self.assertEqual(text.returncode, 0)
                    self.assertEqual(text.stdout.splitlines(), [
                        f"{path}:{line}: WARN: {rule}: {finding['message']}", "", "0 fail, 1 warn, 1 file(s)",
                    ])
                    self.assertEqual(json.loads(run("--json", path).stdout), {"findings": [], "files": 1})

    def test_no_targets_become_findings_in_craft_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = write(root, "readme.md", "Lorem ipsum\n")
            docs = root / "docs"
            write(docs, "guide.md", "Lorem ipsum\n")
            for flags in (("--craft", "--json"), ("--craft", "--json", "--warn-only")):
                with self.subTest(flags=flags):
                    proc = run(*flags, readme, docs)
                    self.assertEqual((proc.returncode, proc.stderr), (0, ""))
                    report = json.loads(proc.stdout)
                    self.assertEqual(report["files"], 0)
                    self.assertEqual(
                        [(f["path"], f["line"], f["severity"], f["rule"]) for f in report["findings"]],
                        [(str(readme), 0, "WARN", "scan-incomplete"), (str(docs), 0, "WARN", "scan-incomplete")],
                    )
                    self.assertIn(LOOKED_FOR, report["findings"][0]["message"])
            proc = run("--craft", readme)
            self.assertEqual((proc.returncode, proc.stderr), (0, ""))
            lines = proc.stdout.splitlines()
            self.assertTrue(lines[0].startswith(f"{readme}:0: WARN: scan-incomplete: no UI files found"))
            self.assertEqual(lines[1:], ["", "0 fail, 1 warn, 0 file(s)"])

    def test_no_targets_keep_legacy_behavior_without_craft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readme = write(Path(tmp), "readme.md", "Lorem ipsum\n")
            for flags in ((), ("--json",), ("--warn-only",), ("--json", "--warn-only")):
                with self.subTest(flags=flags):
                    proc = run(*flags, readme, tmp)
                    self.assertEqual((proc.returncode, proc.stdout), (0, ""))
                    self.assertEqual(proc.stderr, f"no UI files found {LOOKED_FOR}\n")

    def test_unmatched_input_is_reported_beside_scanned_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = write(root, "readme.md", "x\n")
            css = write(root, "a.css", ".a { transition: all 1s; }\n")
            report = json.loads(run("--craft", "--json", readme, css, readme).stdout)
            self.assertEqual(report["files"], 1)
            self.assertEqual([(f["path"], f["rule"]) for f in report["findings"]],
                             [(str(readme), "scan-incomplete"), (str(css), "long-transition"),
                              (str(css), "transition-all"), (str(readme), "scan-incomplete")])

    def test_legacy_fail_still_sets_the_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), "a.tsx", '<p className="transition-all">Lorem ipsum</p>\n')
            proc = run("--craft", "--json", path)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual([f["rule"] for f in json.loads(proc.stdout)["findings"]],
                             ["lorem-ipsum", "transition-all"])
            self.assertEqual(run("--craft", "--warn-only", path).returncode, 0)

    def test_clean_fixture_in_craft_mode(self) -> None:
        proc = run("--craft", "--json", FIXTURES / "clean.tsx")
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))
        self.assertEqual(json.loads(proc.stdout), {"findings": [], "files": 1})

    def test_help_describes_craft(self) -> None:
        proc = run("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--craft", proc.stdout)


class TestCraftFixtures(unittest.TestCase):
    FIXTURE_EXPECTED = {
        "craft_warn.css": [("transition-all", 4), ("transition-all", 8), ("long-transition", 12),
                           ("infinite-animation", 18), ("focus-outline-reset", 22)],
        "craft_quiet.css": [],
        "craft_component.vue": TestComponentStyleBlocks.EXPECTED,
    }

    def test_fixtures_with_craft(self) -> None:
        for name, expected in self.FIXTURE_EXPECTED.items():
            with self.subTest(fixture=name):
                proc = run("--craft", "--json", FIXTURES / name)
                self.assertEqual((proc.returncode, proc.stderr), (0, ""))
                findings = json.loads(proc.stdout)["findings"]
                self.assertEqual([(f["rule"], f["line"]) for f in findings], expected)
                self.assertTrue(all(f["severity"] == "WARN" for f in findings))

    def test_fixtures_without_craft_report_no_craft_rules(self) -> None:
        paths = [FIXTURES / name for name in self.FIXTURE_EXPECTED]
        for flags in ((), ("--json",)):
            with self.subTest(flags=flags):
                proc = run(*flags, *paths)
                self.assertEqual((proc.returncode, proc.stderr), (0, ""))
                for rule in CRAFT_RULES:
                    self.assertNotIn(rule, proc.stdout)

    def test_repeated_runs_are_identical_and_targets_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in self.FIXTURE_EXPECTED:
                write(root, name, (FIXTURES / name).read_bytes())
            original = {path: path.read_bytes() for path in root.iterdir()}
            for flags in (("--craft",), ("--craft", "--json")):
                with self.subTest(flags=flags):
                    first = run(*flags, root, root / "missing.md")
                    second = run(*flags, root, root / "missing.md")
                    self.assertEqual(first.returncode, 0)
                    self.assertEqual((first.returncode, first.stdout, first.stderr),
                                     (second.returncode, second.stdout, second.stderr))
                    self.assertEqual({path: path.read_bytes() for path in root.iterdir()}, original)

    def test_craft_findings_are_sorted_after_legacy_findings(self) -> None:
        content = ('<p className="transition-all">Lorem ipsum</p>\n<style>\n.b:focus { outline: 0; }\n'
                   ".a { transition: opacity 2s; }\n</style>\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), "a.html", content)
            findings = slop_check.check_file(path, craft=True)
            self.assertEqual(findings[: len(slop_check.check_file(path))], slop_check.check_file(path))
            craft_part = [(f.line, f.rule) for f in findings if f.rule in CRAFT_RULES]
            self.assertEqual(craft_part, sorted(craft_part))
            self.assertEqual(craft_part, [(1, "transition-all"), (3, "focus-outline-reset"),
                                          (4, "long-transition")])


class TestBoundedScanner(unittest.TestCase):
    """Unterminated constructs must finish in linear time, even near the size cap."""

    LINE = "x" * 1_990

    def time_check(self, name: str, content: str) -> float:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), name, content)
            start = time.perf_counter()
            slop_check.check_file(path, craft=True)
            return time.perf_counter() - start

    def test_unterminated_constructs(self) -> None:
        cases = (
            ("comment", "a.css", ".a { color: red; }\n/*" + (self.LINE + "\n") * 480),
            ("escaped string", "a.css", '.a { content: "' + (self.LINE + "\\\n") * 480),
            ("string per line", "a.css", ('.a { content: "' + self.LINE[:1_900] + "\n") * 480),
            ("declaration", "a.css", ".a { transition: " + ("opacity 1s, " * 160 + "\n") * 480),
            ("style block", "a.vue", "<style>\n.a { content: '" + (self.LINE + "\n") * 480),
            ("class attribute", "a.html", '<p class="' + ("transition-all " * 130 + "\n") * 480),
            ("unclosed :not() in a focus reset", "a.css",
             ".a:focus" + (":not(" * 398 + "\n") * 480 + "{ outline: none; }"),
        )
        for label, name, content in cases:
            with self.subTest(case=label):
                elapsed = self.time_check(name, content)
                self.assertLess(elapsed, 1.0, f"{label} took {elapsed:.2f}s")

    def test_long_selector_over_many_declarations(self) -> None:
        # A rule's selector is classified once, not once per declaration.
        selector = ("y" * 1_990 + "\n") * 240
        body = ("outline: none;" * 130 + "\n") * 240
        for label, prelude in (("no focus", ".a"), ("focus", ".a:focus ")):
            content = prelude + selector + "{" + body
            with self.subTest(case=label):
                self.assertLess(len(content.encode("utf-8")), slop_check.MAX_FILE_BYTES)
                elapsed = self.time_check("a.css", content)
                self.assertLess(elapsed, 2.0, f"{label} took {elapsed:.2f}s")


if __name__ == "__main__":
    unittest.main()
