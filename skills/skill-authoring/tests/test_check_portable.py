#!/usr/bin/env python3
"""check_portable.py: each rule fires on the construct and stays quiet on its fix.
Run: python3 -m unittest discover -s tests
"""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_portable  # noqa: E402

INTERP = "/usr/bin/" + "python3"   # joined so this file does not trip its own rule


class Lint(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def rules(self, source, name="tool.py"):
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(textwrap.dedent(source).encode("utf-8"))
        return [rule for _, rule, _ in check_portable.lint_file(path)]

    def test_posix_attr_fires_and_getattr_passes(self):
        self.assertEqual(self.rules("import os\nos.open('x', os.O_NOFOLLOW)\n"), ["posix-attr"])
        self.assertEqual(self.rules("import os\nos.open('x', getattr(os, 'O_NOFOLLOW', 0))\n"), [])

    def test_posix_attr_under_a_platform_check_passes(self):
        src = "import os, sys\nif sys.platform != 'win32':\n    os.killpg(1, 9)\n"
        self.assertEqual(self.rules(src), [])

    def test_posix_import_fires_unless_in_a_try(self):
        self.assertEqual(self.rules("import fcntl\n"), ["posix-import"])
        self.assertEqual(self.rules("try:\n    import fcntl\nexcept ImportError:\n    fcntl = None\n"), [])

    def test_text_writes(self):
        self.assertEqual(self.rules("from pathlib import Path\nPath('a').write_text('x')\n"),
                         ["text-write"])
        self.assertEqual(self.rules("open('a', 'w', encoding='utf-8')\n"), ["text-write"])
        self.assertEqual(self.rules("import os\nos.fdopen(3, 'a+', encoding='utf-8')\n"), ["text-write"])
        self.assertEqual(self.rules("from pathlib import Path\nPath('a').open('x')\n"), ["text-write"])

    def test_text_write_fixes_pass(self):
        self.assertEqual(self.rules("open('a', 'w', encoding='utf-8', newline='\\n')\n"), [])
        self.assertEqual(self.rules("from pathlib import Path\nPath('a').write_bytes(b'x')\n"), [])
        self.assertEqual(self.rules("open('a', 'wb')\nopen('a')\nopen('a', 'r')\n"), [])

    def test_console_utf8(self):
        script = "def main():\n    print('x')\n\nif __name__ == '__main__':\n    main()\n"
        self.assertEqual(self.rules(script), ["console-utf8"])
        fixed = script.replace("    main()", "    sys.stdout.reconfigure(encoding='utf-8')\n    main()")
        self.assertEqual(self.rules(fixed), [])

    def test_fixed_interpreter(self):
        self.assertEqual(self.rules(f"CMD = ['{INTERP}', '-V']\n"), ["fixed-interpreter"])

    def test_tests_skip_writes_and_console_but_not_posix(self):
        src = "import os\nopen('a', 'w')\nos.getuid()\nif __name__ == '__main__':\n    print(1)\n"
        self.assertEqual(self.rules(src, "tests/test_x.py"), ["posix-attr"])

    def test_exemption_on_the_line_or_above(self):
        self.assertEqual(self.rules("open('a', 'w')  # portable: exempt fixture\n"), [])
        self.assertEqual(self.rules("# portable: exempt fixture\nopen('a', 'w')\n"), [])

    def test_an_unparseable_file_is_never_clean(self):
        self.assertEqual(self.rules("def (:\n"), ["unparsed"])

    def test_cli_exit_codes(self):
        bad = self.tmp / "bad.py"
        bad.write_bytes(b"open('a', 'w')\n")
        good = self.tmp / "good.py"
        good.write_bytes(b"x = 1\n")
        run = lambda p: subprocess.run([sys.executable, str(SCRIPTS / "check_portable.py"), str(p)],
                                       capture_output=True, text=True, timeout=60)
        self.assertEqual(run(bad).returncode, 1)
        self.assertEqual(run(good).returncode, 0)
        self.assertEqual(run(self.tmp / "missing.py").returncode, 2)


if __name__ == "__main__":
    unittest.main()
