#!/usr/bin/env python3
"""Structural tests for render_probe.js and tests for render_canary_compare.py.

    python3 -B -m unittest discover -s skills/frontend-aesthetics/tests -p 'test_render_probe.py'

The probe runs only inside a browser, so these tests check its shape, its
documented schema, and its read-only contract statically. The live canary pages
in fixtures/render/ are the behavioral check; the comparator is tested here with
synthetic probe output built from expected.json.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "scripts" / "render_probe.js"
CONTRAST = ROOT / "scripts" / "check_contrast.py"
RENDER = ROOT / "tests" / "fixtures" / "render"
COMPARE = ROOT / "tests" / "render_canary_compare.py"

CHECKS = ("overflow", "contrast", "targets", "smallText", "images", "animations", "fonts", "focus")
WIDTHS = ("320", "1440")
PAGES = ("defects.html", "clean.html")

# Read-only contract: none of these may appear in the probe outside comments.
FORBIDDEN = {
    "DOM insertion or removal":
        r"\.(?:append\w*|prepend|remove\w*|insertBefore|replaceChild\w*|replaceWith|insertAdjacent\w*|before|after)\s*\(",
    "attribute write": r"\.(?:setAttribute\w*|toggleAttribute)\s*\(",
    "style or content write": r"\.style\b|\.(?:className|id|textContent|innerText|nodeValue|value)\s*=(?!=)|classList\.",
    "focus change": r"\.(?:focus|blur)\s*\(",
    "scrolling": r"\bscroll(?:To|By|IntoView\w*)\b|\.scroll\s*\(|\bscroll(?:Top|Left)\s*=(?!=)",
    "click or event": r"\bclick\b|\bdispatchEvent\b",
    "navigation": r"\blocation\b|\bhistory\b|\bwindow\.open\b|\.submit\s*\(",
    "network": r"\bfetch\b|\bXMLHttpRequest\b|\bsendBeacon\b|\bWebSocket\b|\bimport\s*\(",
    "storage": r"\blocalStorage\b|\bsessionStorage\b|\bindexedDB\b|document\.cookie",
    "code evaluation": r"\beval\b|\bnew\s+Function\b",
    "HTML write": r"\binnerHTML\b|\bouterHTML\b|document\.write",
    "font loading": r"fonts\.load\b",
    "unbounded loop": r"\bwhile\b|for\s*\(\s*;\s*;",
}


def probe_text() -> str:
    return PROBE.read_text(encoding="utf-8")


def leading_comment_and_body(text: str) -> tuple[str, str]:
    match = re.match(r"\s*/\*(.*?)\*/", text, re.S)
    if match is None:
        return "", text.strip()
    return match.group(1), text[match.end():].strip()


def code_only(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"(?m)(^|\s)//[^\n]*", r"\1", text)


def expectations() -> dict:
    return json.loads((RENDER / "expected.json").read_text(encoding="utf-8"))


def synthetic(page: str, width: str) -> dict:
    """Build a probe result that meets one page-width expectation exactly."""
    spec = expectations()["pages"][page][width]
    checks: dict[str, dict] = {}
    for name, want in spec["checks"].items():
        items: list[dict] = [{"sel": f"div#{seed}:nth-of-type(1)"} for seed in want.get("items", [])]
        for item, seed in zip(items, want.get("items", [])):
            if seed in want.get("reasons", {}):
                item["reasons"] = list(want["reasons"][seed])
        items += [{"sel": f"p#{seed}:nth-of-type(1)", "unmeasurable": True, "reason": "background-image"}
                  for seed in want.get("unmeasurable", [])]
        check: dict = {"status": want["status"], "count": len(items), "items": items}
        if "inline" in want:
            check["inline"] = [{"sel": f"a#{seed}:nth-of-type(1)"} for seed in want["inline"]]
        checks[name] = check
    viewport = {"innerWidth": int(width), "innerHeight": 800, "dpr": 1}
    return {"probe": "render_probe/1", "viewport": viewport, "truncated": False, "checks": checks}


def compare(page: str, width: str, output: object, raw: str | None = None) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "probe.json"
        path.write_text(raw if raw is not None else json.dumps(output), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-B", str(COMPARE), "--page", page, "--width", width, str(path)],
            capture_output=True, text=True, timeout=30,
        )


class TestProbeShape(unittest.TestCase):
    def test_single_arrow_function_after_comment(self) -> None:
        comment, body = leading_comment_and_body(probe_text())
        self.assertTrue(comment, "probe must open with a /* ... */ usage block")
        self.assertRegex(body, r"^\(\)\s*=>\s*\{")
        self.assertTrue(body.endswith("}"), "nothing may follow the function, not even a semicolon")

    def test_under_400_lines(self) -> None:
        self.assertLess(len(probe_text().splitlines()), 400)

    def test_no_forbidden_tokens_outside_comments(self) -> None:
        code = code_only(probe_text())
        for label, pattern in FORBIDDEN.items():
            with self.subTest(label):
                self.assertIsNone(re.search(pattern, code), f"{label}: {re.search(pattern, code)}")

    def test_only_detached_canvas_is_created(self) -> None:
        calls = re.findall(r"createElement\s*\(\s*([^)]*)\)", code_only(probe_text()))
        self.assertTrue(all(arg.strip() in ("'canvas'", '"canvas"') for arg in calls), calls)

    def test_checks_documented_and_implemented(self) -> None:
        comment, body = leading_comment_and_body(probe_text())
        match = re.search(r"checks:\s*\{([^}]*)\}", comment)
        self.assertIsNotNone(match, "usage block must document the checks object")
        documented = tuple(name.strip() for name in match.group(1).split(","))
        self.assertEqual(documented, CHECKS)
        code = code_only(body)
        for name in CHECKS:
            with self.subTest(name):
                self.assertRegex(code, rf"\brun\(\s*'{name}'")

    def test_usage_block_names_the_workflow(self) -> None:
        comment, _ = leading_comment_and_body(probe_text())
        for phrase in ("http://127.0.0.1", "browser_resize", "Tab", "browser_evaluate", "untrusted"):
            with self.subTest(phrase):
                self.assertIn(phrase, comment)

    def test_contrast_formula_matches_check_contrast(self) -> None:
        code = code_only(probe_text())
        helper = CONTRAST.read_text(encoding="utf-8")
        for constant in ("0.04045", "12.92", "0.055", "1.055", "2.4", "0.2126", "0.7152", "0.0722", "0.05"):
            with self.subTest(constant):
                self.assertIn(constant, code)
                self.assertIn(constant, helper)
        for threshold in (r">= 24\b", r">= 18\.66\b", r">= 700\b", r"\? 3 : 4\.5\b"):
            with self.subTest(threshold):
                self.assertRegex(code, threshold)

    def test_probe_emits_fields_the_comparator_reads(self) -> None:
        code = code_only(probe_text())
        self.assertIn("'render_probe/1'", code)
        self.assertEqual(expectations()["probe"], "render_probe/1")
        for field in (r"\bsel:", r"unmeasurable: true", r"\binline\b", r"\breasons\b", r"\binnerWidth:", r"\btruncated:"):
            with self.subTest(field):
                self.assertRegex(code, field)

    @unittest.skipUnless(shutil.which("node"), "node is not on PATH; syntax check skipped")
    def test_node_accepts_it_as_script_and_as_evaluate_argument(self) -> None:
        check = subprocess.run(["node", "--check", str(PROBE)], capture_output=True, text=True, timeout=60)
        self.assertEqual(check.returncode, 0, check.stderr)
        # Playwright wraps the trimmed argument in parentheses and compiles it before running it.
        wrap = "new Function('(' + require('fs').readFileSync(process.argv[1], 'utf8').trim() + ')')"
        compiled = subprocess.run(["node", "-e", wrap, str(PROBE)], capture_output=True, text=True, timeout=60)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)


class TestCanaryFixtures(unittest.TestCase):
    def test_expectations_cover_every_page_width_and_check(self) -> None:
        pages = expectations()["pages"]
        self.assertEqual(tuple(pages), PAGES)
        for page in PAGES:
            self.assertEqual(tuple(pages[page]), WIDTHS)
            for width in WIDTHS:
                with self.subTest(page=page, width=width):
                    spec = pages[page][width]
                    self.assertEqual(tuple(spec["checks"]), CHECKS)
                    self.assertEqual(spec["tabPresses"], 1)
                    self.assertTrue(spec["focusMeasured"])
        for width in WIDTHS:
            clean = pages["clean.html"][width]
            self.assertTrue(clean["noFindings"])
            self.assertFalse([n for n, c in clean["checks"].items() if c["status"] == "findings"])

    def test_every_expected_seed_exists_and_every_defect_seed_is_expected(self) -> None:
        pages = expectations()["pages"]
        for page in PAGES:
            html = (RENDER / page).read_text(encoding="utf-8")
            ids = set(re.findall(r'\bid="(seed-[\w-]+)"', html))
            named = {seed for width in WIDTHS for check in pages[page][width]["checks"].values()
                     for key in ("items", "unmeasurable", "inline", "notItems") for seed in check.get(key, [])}
            with self.subTest(page):
                self.assertLessEqual(named, ids, f"expected.json names ids missing from {page}")
                if page == "defects.html":
                    self.assertEqual(ids, named, "every seeded defect must be expected somewhere")

    def test_pages_are_self_contained_ascii(self) -> None:
        for page in PAGES:
            html = (RENDER / page).read_text(encoding="utf-8")
            with self.subTest(page):
                self.assertTrue(html.isascii(), "no em dashes, emojis, or other non-ASCII text")
                self.assertNotRegex(html, r"(?i)https?:|//[\w.-]+\.\w|@import|@font-face|url\(|<script|<iframe|<link\s+rel=\"stylesheet")
                for attr in re.findall(r'\b(?:src|href|srcset|poster|action)="([^"]*)"', html):
                    self.assertTrue(attr.startswith(("data:", "#")), attr[:40])


class TestCanaryCompare(unittest.TestCase):
    def test_synthetic_pass_for_every_page_and_width(self) -> None:
        for page in PAGES:
            for width in WIDTHS:
                with self.subTest(page=page, width=width):
                    proc = compare(page, width, synthetic(page, width))
                    self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                    self.assertEqual(proc.stdout.strip(), "PASS")

    def test_json_string_of_the_object_is_accepted(self) -> None:
        out = synthetic("defects.html", "320")
        proc = compare("defects.html", "320", None, raw=json.dumps(json.dumps(out)))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_missing_seeded_finding_fails(self) -> None:
        out = synthetic("defects.html", "320")
        out["checks"]["targets"]["items"] = []
        proc = compare("defects.html", "320", out)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("targets: seed-icon-button missing from items", proc.stdout)
        self.assertEqual(proc.stdout.strip().splitlines()[-1], "FAIL")

    def test_unmeasurable_seed_counted_as_a_ratio_fails(self) -> None:
        out = synthetic("defects.html", "1440")
        for item in out["checks"]["contrast"]["items"]:
            item.pop("unmeasurable", None)
        proc = compare("defects.html", "1440", out)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("seed-gradient-text missing from unmeasurable items", proc.stdout)

    def test_inline_link_listed_as_a_candidate_fails(self) -> None:
        out = synthetic("defects.html", "320")
        out["checks"]["targets"]["items"].append({"sel": "a#seed-inline-link:nth-of-type(1)"})
        proc = compare("defects.html", "320", out)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("seed-inline-link must not appear in items", proc.stdout)

    def test_wrong_image_reason_fails(self) -> None:
        out = synthetic("defects.html", "320")
        out["checks"]["images"]["items"][1]["reasons"] = ["broken"]
        proc = compare("defects.html", "320", out)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("seed-img-upscaled reasons", proc.stdout)

    def test_unexpected_finding_on_clean_page_fails(self) -> None:
        out = synthetic("clean.html", "1440")
        out["checks"]["smallText"]["status"] = "findings"
        out["checks"]["smallText"]["items"] = [{"sel": "p.note:nth-of-type(3)", "fontSize": 11}]
        proc = compare("clean.html", "1440", out)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("smallText: status is \"findings\"", proc.stdout)
        self.assertIn("clean page may not report findings", proc.stdout)

    def test_unlisted_check_with_findings_on_clean_page_fails(self) -> None:
        out = synthetic("clean.html", "320")
        out["checks"]["extra"] = {"status": "findings", "items": []}
        proc = compare("clean.html", "320", out)
        self.assertEqual(proc.returncode, 1)

    def test_mismatched_inner_width_fails(self) -> None:
        out = copy.deepcopy(synthetic("defects.html", "320"))
        out["viewport"]["innerWidth"] = 500
        proc = compare("defects.html", "320", out)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("viewport.innerWidth is 500, expected 320", proc.stdout)

    def test_unfocused_page_gets_the_tab_hint(self) -> None:
        out = synthetic("clean.html", "320")
        out["checks"]["focus"] = {"status": "unmeasurable", "items": [], "reason": "no focused element"}
        proc = compare("clean.html", "320", out)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("press Tab 1 time(s)", proc.stdout)

    def test_bad_input_exits_2(self) -> None:
        self.assertEqual(compare("defects.html", "320", None, raw="{not json").returncode, 2)
        self.assertEqual(compare("defects.html", "320", None, raw="[1, 2]").returncode, 2)
        self.assertEqual(compare("defects.html", "768", synthetic("defects.html", "320")).returncode, 2)
        self.assertEqual(compare("other.html", "320", synthetic("defects.html", "320")).returncode, 2)


if __name__ == "__main__":
    unittest.main()
