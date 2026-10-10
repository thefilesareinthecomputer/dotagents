#!/usr/bin/env python3
"""Tests for scrub.py. Every secret and term here is invented."""

import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("scrub", HERE.parent / "scripts" / "scrub.py")
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

TERMS = {"Zebrafish", "qx9corp", "#yoyo", "two words"}

# Every fake credential is assembled at runtime from halves, so this file never holds a credential-shaped
# literal that a scanner (or a reader) could mistake for an issued one. The values are invented.
AWS = "AKIA" + "IOSFODNN7EXAMPLE"          # AWS's own documentation example key
OPENAI = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
ANTHROPIC = "sk-ant-" + "api03-abcdefghijklmnopqrstuvwxyz"
GITHUB = "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789"
SLACK = "xoxb-" + "123456789012-abcdefghij"
JWT = "eyJhbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "." + "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
DB_URL = "postgres://admin:" + "hunter2hunter2" + "@db.internal:5432/app"
PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA " + "PRIVATE KEY-----"


class TestSecrets(unittest.TestCase):
    def check(self, text, why, keep=()):
        counts = {}
        out = sc.scrub_text(text, set(), counts)
        self.assertIn(why, counts, (text, counts))
        self.assertIn(sc.SECRET, out)
        for k in keep:
            self.assertIn(k, out)
        return out

    def test_shapes(self):
        self.check("aws_access_key_id = " + AWS, "aws access key")
        self.check("export OPENAI_API_KEY=" + OPENAI, "api key", keep=["OPENAI_API_KEY="])
        self.check("ANTHROPIC_API_KEY=" + ANTHROPIC, "api key")
        self.check("token " + GITHUB, "github token")
        self.check(SLACK, "slack token")
        self.check("curl -H 'Authorization: Bearer abcdefghijklmnopqrstuvwxyz' x", "bearer token", keep=["Authorization: Bearer "])
        self.check(DB_URL, "url password", keep=["postgres://admin:", "@db.internal"])
        self.check(PEM, "private key")
        self.check("DB_PASSWORD='correct-horse-battery'", "key-like assignment", keep=["DB_PASSWORD="])
        self.check(JWT, "jwt")
        self.check("aws configure set aws_access_key_id " + "ASIA" + "IOSFODNN7EXAMPLE", "aws access key")
        self.check("tool login --password correct-horse-battery --user me", "flag credential", keep=["--password ", "--user me"])
        self.check("tool --token=abcdefghijklmnop", "flag credential", keep=["--token="])
        self.check("curl -u admin:hunter2hunter2 https://host.example/", "basic-auth password", keep=["-u admin:", "https://host.example/"])
        self.check("mysql -h db.example -u root -pcorrecthorse app", "inline password flag", keep=["-u root -p", " app"])

    def test_plain_commands_are_untouched(self):
        for text in ("git status --porcelain", "python3 -m unittest discover -s tests", "ls -la ~/.config",
                     "echo key=value", "export PATH=/usr/bin", "token count is 12", "the secret sauce",
                     "pip install -p python3.11 requests", "git log -p HEAD~1", "ls -u -t ."):
            counts = {}
            self.assertEqual(sc.scrub_text(text, set(), counts), text, text)
            self.assertEqual(counts, {}, text)


class TestTerms(unittest.TestCase):
    def test_terms_are_masked_by_the_hook_rule(self):
        counts = {}
        out = sc.scrub_text("notes on Zebrafish and zebrafish and QX9CORP and #yoyo and two words", TERMS, counts)
        self.assertNotIn("Zebrafish", out)
        self.assertIn("zebrafish", out, "a mixed-case term matches as typed only")
        self.assertNotIn("QX9CORP", out, "a single-case term matches any case")
        self.assertNotIn("#yoyo", out)
        self.assertNotIn("two words", out)
        self.assertEqual(counts["term"], 4)

    def test_term_inside_a_word_is_left(self):
        self.assertEqual(sc.scrub_text("qx9corporation", TERMS), "qx9corporation")

    def test_structured_values_are_walked(self):
        counts = {}
        out = sc.scrub_value({"a": ["Zebrafish", 1, {"b": AWS}], "c": None}, TERMS, counts)
        self.assertEqual(out, {"a": [sc.TERM, 1, {"b": sc.SECRET}], "c": None})
        self.assertEqual(counts, {"term": 1, "aws access key": 1})

    def test_no_terms_file_means_no_terms(self):
        import os
        old = os.environ.get("IDENTIFIER_TERMS_FILE")
        os.environ["IDENTIFIER_TERMS_FILE"] = "/nonexistent/terms.txt"
        try:
            self.assertEqual(sc.load_terms(), set())
        finally:
            if old is None:
                del os.environ["IDENTIFIER_TERMS_FILE"]
            else:
                os.environ["IDENTIFIER_TERMS_FILE"] = old


if __name__ == "__main__":
    unittest.main()
