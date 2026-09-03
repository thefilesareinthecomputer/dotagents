"""The published set carries no literal invisible or display-reordering codepoint.

Detectors and their tests write such codepoints as escapes (see the docstring
of unicode_smuggle_check.py): a literal is invisible in its own source and
fails every downstream sweep, including the one run inside the public mirror.
This test fails upstream, before a publish, on the first literal that lands.
Run: python3 -m unittest discover -s tests
"""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "skills" / "my-security-review-checklist" / "scripts" / "unicode_smuggle_check.py"
PUBLISHED = ["agents", "commands", "skills", "specs", "tests", ".github", "sync-skills.sh"]


class PublishedSetHygiene(unittest.TestCase):
    def test_no_literal_invisible_codepoints(self):
        targets = [str(ROOT / p) for p in PUBLISHED if (ROOT / p).exists()]
        targets += [str(p) for p in ROOT.glob("*.md")]
        proc = subprocess.run([sys.executable, str(SCANNER), *targets],
                              capture_output=True, text=True)
        fails = [line for line in proc.stdout.splitlines() if line.startswith("FAIL")]
        self.assertEqual(fails, [], "\n".join(fails))


if __name__ == "__main__":
    unittest.main()
