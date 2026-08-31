import tempfile
import unittest
from pathlib import Path

from relay.audit import AuditLog


class TestAuditChain(unittest.TestCase):
    def test_chain_survives_reopen_and_detects_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "audit.jsonl")
            log = AuditLog(path)
            log.append("run", {"goal": "a"})
            log.append("run", {"goal": "b"})
            reopened = AuditLog(path)
            reopened.append("run", {"goal": "c"})
            self.assertTrue(reopened.verify_chain().valid)

            lines = Path(path).read_text().splitlines()
            lines[1] = lines[1].replace('"goal":"b"', '"goal":"tampered"')
            Path(path).write_text("\n".join(lines) + "\n")
            report = AuditLog(path).verify_chain()
            self.assertFalse(report.valid)
            self.assertEqual(report.first_break, 1)


if __name__ == "__main__":
    unittest.main()
