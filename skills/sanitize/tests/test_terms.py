#!/usr/bin/env python3
"""Tests for the term-list and secret passes in skills/sanitize/scripts/sanitize.py.

Stdlib unittest. Every term here is invented; the station term list is never read,
because IDENTIFIER_TERMS_FILE points at a fixture written by the test.
Run: python3 -m unittest discover -s skills/sanitize/tests -v
"""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "sanitize.py"

spec = importlib.util.spec_from_file_location("sanitize", SCRIPT)
sz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sz)


class TermFixture(unittest.TestCase):
    """A temp term list with invented words, wired through the env var the engine reads."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.terms_path = Path(self.tmp.name) / "terms.txt"
        self.terms_path.write_text("# a comment line\nzorbulate\nQuintaxia\n#tagword\n\n", encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {"IDENTIFIER_TERMS_FILE": str(self.terms_path)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class TestTermList(TermFixture):
    def test_loads_terms_and_skips_comments(self):
        self.assertEqual(sz.station_terms(), {"zorbulate", "Quintaxia", "#tagword"})

    def test_missing_list_refuses(self):
        os.environ["IDENTIFIER_TERMS_FILE"] = str(Path(self.tmp.name) / "nowhere.txt")
        with self.assertRaises(sz.SanitizeError) as cm:
            sz.station_terms()
        self.assertEqual(cm.exception.code, 2)

    def test_an_empty_list_refuses_too(self):
        # a list of comments and blank lines silently disables the backstop; it fails closed instead
        self.terms_path.write_text("# nothing here\n\n", encoding="utf-8")
        with self.assertRaises(sz.SanitizeError) as cm:
            sz.station_terms()
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("no terms", str(cm.exception))

    def test_short_terms_match_as_typed_only(self):
        # an all-caps two-letter term under the any-case rule matches the common word; below the
        # short-term length a term matches as typed, and the normalized view skips it already
        counts = {}
        out = sz.scrub_text("the ab test, AB (DE1) aside, and Ab", {"AB"}, counts)
        self.assertEqual(out, "the ab test, [ROLE] aside, and Ab")
        self.assertNotIn("term", counts)
        self.assertEqual(sz.scrub_text("AB owns it", {"AB"}, {}), "[TERM] owns it")
        self.assertEqual(sz.scrub_text("ZOR and zor", {"zor"}, {}), "ZOR and [TERM]")
        self.assertEqual(sz.scrub_text("ZORB and zorb", {"zorb"}, {}), "[TERM] and [TERM]")   # four characters is the floor

    def test_single_case_term_matches_any_case(self):
        counts = {}
        out = sz.scrub_text("ZORBULATE and Zorbulate and zorbulate", {"zorbulate"}, counts)
        self.assertEqual(out, "[TERM] and [TERM] and [TERM]")
        self.assertEqual(counts["term"], 3)

    def test_mixed_case_term_matches_as_typed_only(self):
        counts = {}
        out = sz.scrub_text("Quintaxia met quintaxia", {"Quintaxia"}, counts)
        self.assertEqual(out, "[TERM] met quintaxia")
        self.assertEqual(counts["term"], 1)

    def test_symbol_edged_term_matches_whole(self):
        out = sz.scrub_text("see #tagword here", {"#tagword"}, {})
        self.assertEqual(out, "see [TERM] here")

    def test_term_inside_a_word_does_not_match(self):
        out = sz.scrub_text("zorbulates", {"zorbulate"}, {})
        self.assertEqual(out, "zorbulates")

    def test_longer_terms_win_over_shorter(self):
        out = sz.scrub_text("zorbulate corp", {"zorbulate", "zorbulate corp"}, {})
        self.assertEqual(out, "[TERM]")

    def test_extra_terms_report_under_their_own_class(self):
        counts = {}
        out = sz.scrub_text("blorf and zorbulate", {"zorbulate"}, counts, extra_terms={"blorf"})
        self.assertEqual(out, "[TERM] and [TERM]")
        self.assertEqual(counts, {"term": 1, "ban": 1})

    def test_extra_patterns_report_as_pattern(self):
        counts = {}
        out = sz.scrub_text("ticket ABC-12345 open", set(), counts, extra_patterns=[r"\bABC-\d{5}\b"])
        self.assertEqual(out, "ticket [PATTERN] open")
        self.assertEqual(counts, {"pattern": 1})


class TestSecrets(unittest.TestCase):
    def test_private_key_block_is_one_hit(self):
        text = "x\n-----BEGIN RSA PRIVATE KEY-----\nabc\ndef\n-----END RSA PRIVATE KEY-----\ny"
        counts = {}
        out = sz.scrub_text(text, set(), counts)
        self.assertEqual(out, "x\n[SECRET]\ny")
        self.assertEqual(counts["secret"], 1)

    def test_vendor_prefixed_key(self):
        out = sz.scrub_text("key sk-ant-" + "a" * 24 + " end", set(), {})
        self.assertEqual(out, "key [SECRET] end")

    def test_key_like_assignment_masks_only_the_value(self):
        out = sz.scrub_text("API_TOKEN=abc9defghijkl", set(), {})
        self.assertEqual(out, "API_TOKEN=[SECRET]")

    def test_key_like_names_in_code_are_left_alone(self):
        code = "key = parts[0]\ntokens = text.split()\nAPI_KEY = os.environ.get(name)\npath_tokens = segments\n"
        self.assertEqual(sz.scrub_text(code, set(), {}), code)

    def test_url_password_masks_only_the_password(self):
        out = sz.scrub_text("postgres://user:hunter22@db/x", set(), {})
        self.assertEqual(out, "postgres://user:[SECRET]@db/x")

    def test_encoded_runs_are_checked_for_every_shape_not_terms_only(self):
        import base64
        key = base64.b64encode(b"API_TOKEN=abc9defghijklmnop").decode()
        counts = {}
        self.assertEqual(sz.scrub_text(f"blob {key} end", set(), counts), "blob [SECRET] end")
        self.assertEqual(counts, {"secret-encoded": 1})
        mail = base64.b64encode(b"write to someone@example.test today").decode()
        counts = {}
        self.assertEqual(sz.scrub_text(f"blob {mail} end", set(), counts), "blob [EMAIL] end")
        self.assertEqual(counts, {"email-encoded": 1})
        hexed = b"-u admin:hunter22x".hex()
        self.assertEqual(sz.scrub_text(f"x {hexed} y", set(), {}), "x [SECRET] y")

    def test_basic_authorization_is_a_secret_whatever_it_decodes_to(self):
        out = sz.scrub_text("Authorization: Basic dXNlcjpwYXNzd29yZA==", set(), {})
        self.assertEqual(out, "Authorization: Basic [SECRET]")

    def test_already_masked_value_is_not_counted_twice(self):
        counts = {}
        out = sz.scrub_text("API_TOKEN=[SECRET]", set(), counts)
        self.assertEqual(out, "API_TOKEN=[SECRET]")
        self.assertEqual(counts, {})


class TestCustomChecks(unittest.TestCase):
    def test_email(self):
        counts = {}
        out = sz.scrub_text("mail someone@example.test now", set(), counts)
        self.assertEqual(out, "mail [EMAIL] now")
        self.assertEqual(counts, {"email": 1})

    def test_phone(self):
        out = sz.scrub_text("call +1 555-010-0199 today", set(), {})
        self.assertEqual(out, "call [PHONE] today")

    def test_home_path_keeps_the_rest_of_the_path(self):
        # Built from pieces so the fixture never forms the shape on disk.
        mac = "/" + "Users" + "/somebody" + "/dev/repo/x.py"
        linux = "/" + "home" + "/other" + "/y"
        out = sz.scrub_text(f"see {mac} and {linux}", set(), {})
        self.assertEqual(out, "see [HOME]/dev/repo/x.py and [HOME]/y")

    def test_role_code_and_catalog(self):
        counts = {}
        out = sz.scrub_text("AB (DE1) owns prod_bronze", set(), counts)
        self.assertEqual(out, "[ROLE] owns [CATALOG]")
        self.assertEqual(counts, {"role_code": 1, "catalog": 1})

    def test_short_version_like_numbers_are_not_phones(self):
        out = sz.scrub_text("version 2.1.280 and port 8080", set(), {})
        self.assertEqual(out, "version 2.1.280 and port 8080")


class TestAnswerMode(TermFixture):
    def run_cli(self, args, stdin_text=""):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(stdin_text)), redirect_stdout(out), redirect_stderr(err):
            code = sz.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_clean_text_passes_through(self):
        code, out, _ = self.run_cli(["answer"], "the answer is 42\n")
        self.assertEqual(code, 0)
        self.assertEqual(out, "the answer is 42\n")

    def test_term_hit_withholds_whole_answer(self):
        code, out, err = self.run_cli(["answer"], "the owner is zorbulate\n")
        self.assertEqual(code, 3)
        self.assertEqual(out.strip(), "withheld: the answer touched a protected term")
        self.assertNotIn("zorbulate", out + err)

    def test_a_term_inside_a_shape_still_withholds(self):
        # the email pass would replace the whole address first; the term check runs on the original text
        code, out, err = self.run_cli(["answer"], "mail zorbulate@example.test for access\n")
        self.assertEqual(code, 3)
        self.assertNotIn("zorbulate", out + err)

    def test_a_pattern_hit_withholds_too(self):
        code, out, _ = self.run_cli(["answer", "--patterns", r"PRJ-\d{4}"], "ticket PRJ-1234 is open\n")
        self.assertEqual(code, 3)
        self.assertEqual(out.strip(), "withheld: the answer touched a protected pattern")
        code, out, _ = self.run_cli(["answer", "--patterns", r"PRJ-\d{4}"], "no ticket here\n")
        self.assertEqual(code, 0)

    def test_normalized_term_hit_withholds_too(self):
        code, out, err = self.run_cli(["answer"], "the owner is z o r b u l a t e\n")
        self.assertEqual(code, 3)
        self.assertNotIn("z o r b", out + err)

    def test_secret_is_masked_not_withheld(self):
        code, out, _ = self.run_cli(["answer"], "token ghp_" + "A" * 30 + "\n")
        self.assertEqual(code, 0)
        self.assertEqual(out, "token [SECRET]\n")

    def test_missing_station_list_exits_2(self):
        os.environ["IDENTIFIER_TERMS_FILE"] = str(Path(self.tmp.name) / "nowhere.txt")
        code, _, err = self.run_cli(["answer"], "hello\n")
        self.assertEqual(code, 2)
        self.assertIn("term list", err)

    def test_config_adds_terms_patterns_and_a_ban_list(self):
        ban = Path(self.tmp.name) / "ban.txt"
        ban.write_text("flombix\n")
        cfg = Path(self.tmp.name) / "corpus.json"
        cfg.write_text(json.dumps({"ban_list": str(ban), "terms": ["grexon"], "patterns": [r"\bQX-\d{4}\b"]}))
        code, out, _ = self.run_cli(["answer", "--config", str(cfg)], "QX-1234 is fine\n")
        self.assertEqual((code, out), (3, "withheld: the answer touched a protected pattern\n"))   # a pattern the user added is a gate too
        code, out, _ = self.run_cli(["answer", "--config", str(cfg)], "flombix met grexon\n")
        self.assertEqual(code, 3)

    def test_config_with_unknown_keys_refuses(self):
        cfg = Path(self.tmp.name) / "corpus.json"
        cfg.write_text(json.dumps({"terms": [], "masker": "x"}))
        code, _, err = self.run_cli(["answer", "--config", str(cfg)], "hi\n")
        self.assertEqual(code, 2)
        self.assertIn("config", err)

    def test_no_station_terms_flag_runs_without_the_list(self):
        os.environ["IDENTIFIER_TERMS_FILE"] = str(Path(self.tmp.name) / "nowhere.txt")
        code, out, _ = self.run_cli(["answer", "--no-station-terms"], "hello\n")
        self.assertEqual(code, 0)
        self.assertEqual(out, "hello\n")


if __name__ == "__main__":
    unittest.main()
