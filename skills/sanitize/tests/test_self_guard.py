#!/usr/bin/env python3
"""The detector's own files are the easiest place for a real value to hide. This test
runs tree mode over the skill folder with the station term list and the custom shape
checks, and fails on any hit. It never reads the list itself; the engine does. Skipped
where no station list exists (a fresh machine or CI).
Run: python3 -m unittest discover -s skills/sanitize/tests -v
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPT = SKILL / "scripts" / "sanitize.py"


class TestSelfGuard(unittest.TestCase):
    def test_no_station_term_or_personal_shape_in_the_skill(self):
        env = dict(os.environ)
        doctor = subprocess.run([sys.executable, str(SCRIPT), "doctor"], capture_output=True, text=True, env=env)
        if doctor.returncode == 2:
            self.skipTest("no station term list on this machine")
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        res = subprocess.run([sys.executable, str(SCRIPT), "tree", str(SKILL)], capture_output=True, text=True, env=env)
        report = json.loads(res.stdout)
        # The tests plant invented shapes on purpose, and this table names exactly which
        # file holds how many of each class; any hit beyond it, any term-list, ban or path
        # hit anywhere, and any skipped file is an offender.
        expected = {"tests/test_terms.py": {"secret": 6, "email": 3, "phone": 1, "role_code": 2, "catalog": 1},
                    "tests/test_modes.py": {"email": 3}}
        offenders = []
        for entry in report["files_changed"]:
            classes = entry["classes"]
            if any(k.startswith(("term", "ban", "path")) for k in classes):
                offenders.append((entry["path"], classes))
            elif classes != expected.get(entry["path"]):
                offenders.append((entry["path"], classes))
        self.assertEqual(offenders, [], f"hits in the skill's own files beyond the fixture table: {offenders}")
        self.assertEqual(report["skipped"], [], f"unscanned files in the skill: {report['skipped']}")


if __name__ == "__main__":
    unittest.main()
