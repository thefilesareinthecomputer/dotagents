"""The published set carries no literal invisible or display-reordering codepoint,
and no test fixture commits a dependency manifest with pinned versions.

Detectors and their tests write such codepoints as escapes (see the docstring
of unicode_smuggle_check.py): a literal is invisible in its own source and
fails every downstream sweep, including the one run inside the public mirror.
This test fails upstream, before a publish, on the first literal that lands.
Run: python3 -m unittest discover -s tests
"""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "skills" / "my-security-review-checklist" / "scripts" / "unicode_smuggle_check.py"
PUBLISHED = ["agents", "commands", "skills", "lib", "specs", "tests", "app", ".github", "sync-skills.sh"]


class PublishedSetHygiene(unittest.TestCase):
    def test_no_literal_invisible_codepoints(self):
        targets = [str(ROOT / p) for p in PUBLISHED if (ROOT / p).exists()]
        targets += [str(p) for p in ROOT.glob("*.md")]
        proc = subprocess.run([sys.executable, str(SCANNER), *targets],
                              capture_output=True, text=True)
        fails = [line for line in proc.stdout.splitlines() if line.startswith("FAIL")]
        self.assertEqual(fails, [], "\n".join(fails))

    def test_test_fixtures_commit_no_pinned_dependencies(self):
        # Dependency scanners read every committed manifest as a real app's and
        # flag pinned versions with advisories, though nothing installs a fixture.
        # A fixture that needs one writes it at test time (code-kg's fixture_copy.py).
        files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--", *PUBLISHED],
                               capture_output=True, text=True, check=True).stdout.split("\n")
        exact = re.compile(r"^v?\d+(\.\d+)*$")
        pinned = []
        for rel in files:
            parts = rel.split("/")
            if "tests" not in parts[:-1] and not any("fixture" in p for p in parts[:-1]):
                continue
            path = ROOT / rel
            if parts[-1] == "package.json":
                data = json.loads(path.read_text(encoding="utf-8"))
                for key in ("dependencies", "devDependencies", "peerDependencies",
                            "optionalDependencies"):
                    pinned += [f"{rel}: {name} {ver}" for name, ver in data.get(key, {}).items()
                               if exact.match(str(ver).strip())]
            elif re.fullmatch(r"requirements[^/]*\.txt|pyproject\.toml", parts[-1]):
                pinned += [f"{rel}: {line.strip()}"
                           for line in path.read_text(encoding="utf-8").splitlines()
                           if "==" in line and not line.lstrip().startswith("#")]
        self.assertEqual(pinned, [], "\n".join(pinned))


if __name__ == "__main__":
    unittest.main()
