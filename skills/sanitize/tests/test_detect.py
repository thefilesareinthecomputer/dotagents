#!/usr/bin/env python3
"""Tests for detect.py, the one rule source: every class, every allowance, the codepoint
table and the severity tables.

Every detector-shaped value here is joined at runtime, so this file's own source holds
none of the shapes it tests and the self-guard sweep finds nothing in it.
Run: python3 -m unittest discover -s skills/sanitize/tests -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import detect  # noqa: E402

AT = "@"
SLASH_USERS = "/" + "Users/"


def classes(text, terms=None):
    return sorted({h.cls for h in detect.find(text, terms)})


def rules(text):
    return sorted({h.rule for h in detect.find(text) if h.cls == "invisible"})


class TestSecrets(unittest.TestCase):
    def test_vendor_key_with_a_glued_suffix_is_still_a_key(self):
        key = "sk_live_" + "Ab3dEf6hIj9kLm2nOp5q"
        self.assertEqual(classes(f"key: {key}"), ["secret"])
        self.assertEqual(classes(f"key: {key}_xxxx"), ["secret"])
        aws = "AKIA" + "ABCDEFGH23456789"
        self.assertEqual(classes(f"id {aws}_xxxx"), ["secret"])

    def test_restricted_and_webhook_and_slack_refresh_shapes(self):
        for value in ("rk_test_" + "Zx9Zx9Zx9Zx9Zx9Zx9", "whsec_" + "Q1w2E3r4T5y6U7i8O9p0Aa1Ss2",
                      "xoxe-" + "1-ab2cd3ef4gh5"):
            self.assertEqual(classes(f"v = {value} ;"), ["secret"], value)

    def test_quoted_key_form(self):
        text = '{"api_key": "' + "AbCdEf" + "123456GhIjK" + '"}'
        self.assertIn("secret", classes(text))

    def test_stand_in_credentials_are_allowed(self):
        self.assertEqual(classes("postgres://app:" + "app@db:5432/app"), [])
        self.assertEqual(classes("https://user:" + "pw" + AT + "gw.example.com/v1"), [])
        self.assertEqual(classes("postgres://app:" + "Zq8wPl2xVm@db/app"), ["secret"])

    def test_glued_mysql_password_but_not_code(self):
        self.assertEqual(classes("mysql -u root -p" + "Zq8wPl2x db"), ["secret"])
        self.assertEqual(classes("order = sorted(x, key=lambda m: (-points_no_self[m], m))"), [])

    def test_curl_user_password_but_not_a_date_format(self):
        self.assertEqual(classes("curl -u admin:" + "hunter2x9 https://h"), ["secret"])
        self.assertEqual(classes("date -u +%Y-%m-%dT%H:%M:%SZ"), [])

    def test_publishable_key_is_not_a_secret(self):
        self.assertEqual(classes("pk_live_" + "Ab3dEf6hIj9kLm2nOp5q"), [])

    def test_placeholders_clear_the_secret_class_only(self):
        self.assertEqual(classes("sk_test_" + "X" * 20), [])
        self.assertEqual(classes("token " + "{redacted-" + "password}"), [])
        real = "sk_live_" + "Ab3dEf6hIj9kLm2nOp5q" + "_xxxx"
        self.assertEqual(classes(real), ["secret"])

    def test_key_header_alone_is_a_warning_class(self):
        header = "-----" + "BEGIN " + "PRIVATE KEY" + "-----"
        self.assertEqual(classes(header + "\nnot key material\n"), ["key_header"])

    def test_key_header_with_material_under_it_is_a_secret(self):
        header = "-----" + "BEGIN RSA " + "PRIVATE KEY" + "-----"
        body = "MIIEow" + "A" * 58
        self.assertEqual(classes(f"{header}\nProc-Type: 4,ENCRYPTED\n\n{body}\n"), ["secret"])

    def test_whole_pem_block_is_one_secret(self):
        begin = "-----" + "BEGIN " + "PRIVATE KEY" + "-----"
        end = "-----" + "END " + "PRIVATE KEY" + "-----"
        found = detect.find(f"{begin}\nabc\n{end}\n")
        self.assertEqual([h.cls for h in found], ["secret"])


class TestPersonalShapesAndAllowances(unittest.TestCase):
    def test_reserved_domains_clear_email_and_a_real_one_does_not(self):
        self.assertEqual(classes("write to user" + AT + "example.com"), [])
        self.assertEqual(classes("write to user" + AT + "mail.test"), [])
        self.assertEqual(classes("write to user" + AT + "example.com.evil.io"), ["email"])

    def test_a_term_inside_an_allowed_address_is_still_a_term(self):
        found = classes("write to zorbulate" + AT + "example.com", {"zorbulate"})
        self.assertEqual(found, ["term"])

    def test_placeholder_owners_clear_home_path(self):
        self.assertEqual(classes(SLASH_USERS + "me/project"), [])
        self.assertEqual(classes("/" + "home/x/.agents"), [])          # one-letter placeholder
        self.assertEqual(classes(SLASH_USERS + "qz/project"), ["home_path"])   # two letters can be real
        self.assertEqual(classes(SLASH_USERS + "<you>/project"), [])
        self.assertEqual(classes(SLASH_USERS + "qwertz/project"), ["home_path"])
        self.assertEqual(classes("C:" + "\\Users\\" + "qwertz\\project"), ["home_path"])
        self.assertEqual(classes("C:" + "\\Users\\" + "me\\project"), [])

    def test_fictional_phone_is_allowed_and_a_real_shape_is_not(self):
        self.assertEqual(classes("call 312-555-01" + "23"), [])
        self.assertEqual(classes("call 312-867-53" + "09"), ["phone"])

    def test_work_item_ids(self):
        self.assertEqual(classes("see STORY-" + "000037"), [])        # zero-padded counter
        self.assertEqual(classes("see STORY-" + "123456"), [])        # consecutive run
        self.assertEqual(classes("see STORY-" + "583920"), ["work_item"])
        self.assertEqual(classes("see WI-" + "583920"), ["work_item"])

    def test_guid(self):
        self.assertEqual(classes("id " + "3f2b8c1e-" + "9a4d-4e7b-8c2f-1a2b3c4d5e6f"), ["guid"])

    def test_stand_in_guid_is_allowed_and_a_real_one_is_not(self):
        # the version and variant digits are ignored; the rest, in one case, is a
        # padded counter or one repeated digit
        self.assertEqual(classes("id " + "00000000-" + "0000-4000-8000-000000000001"), [])
        self.assertEqual(classes("id " + "00000000-" + "0000-0000-0000-000000000000"), [])
        self.assertEqual(classes("id " + "ffffffff-" + "ffff-ffff-ffff-ffffffffffff"), [])
        self.assertEqual(classes("id " + "11111111-" + "1111-4111-8111-111111111111"), [])
        self.assertEqual(classes("id " + "AAAAAAAA-" + "AAAA-4AAA-8AAA-AAAAAAAAAAAA"), [])
        self.assertEqual(classes("id " + "aaaaaaaa-" + "AaAa-4aaA-8AaA-aAaAaAaAaAaA"), ["guid"])
        self.assertEqual(classes("id " + "00000000-" + "0000-4000-8000-0000000003e8"), ["guid"])
        self.assertEqual(classes("id " + "00000000-" + "0000-4000-8000-00000000a1b2"), ["guid"])
        self.assertEqual(classes("id " + "12345678-" + "1234-5678-1234-567812345678"), ["guid"])

    def test_role_code_and_catalog(self):
        self.assertEqual(classes("owner AB (" + "PM1)"), ["role_code"])
        self.assertEqual(classes("table prod" + "_gold"), ["catalog"])

    def test_hits_never_hold_the_value(self):
        hit = detect.find("user" + AT + "real-domain.io")[0]
        self.assertEqual(set(vars(hit)), {"start", "end", "cls", "rule"})


class TestTerms(unittest.TestCase):
    def test_terms_skip_when_none(self):
        self.assertEqual(classes("zorbulate here", None), [])

    def test_term_views(self):
        views = {h.rule for h in detect.find("zorbulate and z.o.r.b.u.l.a.t.e", {"zorbulate"})}
        self.assertEqual(views, {"raw", "normalized"})

    def test_lenient_list_is_none_when_missing(self):
        old = os.environ.get("IDENTIFIER_TERMS_FILE")
        os.environ["IDENTIFIER_TERMS_FILE"] = "/nonexistent/terms.txt"
        try:
            self.assertIsNone(detect.station_terms_lenient())
        finally:
            if old is None:
                os.environ.pop("IDENTIFIER_TERMS_FILE")
            else:
                os.environ["IDENTIFIER_TERMS_FILE"] = old

    def test_project_aliases_from_engagement_folders(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("Quorvex-okf", "sample-okf", "notes"):
                (Path(d) / "PROJECTS" / name).mkdir(parents=True)
            self.assertEqual(detect.project_aliases(Path(d)), {"Quorvex"})


class TestInvisibles(unittest.TestCase):
    def test_each_rule(self):
        cases = {
            0xE0041: "tag-smuggling", 0x202E: "bidi-override", 0x2066: "bidi-isolate",
            0x200B: "zero-width", 0x2062: "invisible-operator", 0xFE0F: "variation-selector",
            0x00A0: "exotic-space", 0x00AD: "soft-hyphen", 0xE000: "private-use",
            0x0007: "control", 0x2028: "line-separator", 0x3164: "zero-width",
        }
        for cp, rule in cases.items():
            self.assertEqual(rules("a" + chr(cp) + "b"), [rule], hex(cp))

    def test_plain_text_and_whitespace_are_clean(self):
        self.assertEqual(rules("plain text\twith\ttabs\r\nand newlines ok"), [])

    def test_bom_at_the_start_is_an_encoding_marker(self):
        self.assertEqual(rules(chr(0xFEFF) + "text"), [])
        self.assertEqual(rules("te" + chr(0xFEFF) + "xt"), ["zero-width"])

    def test_fold_set_is_the_normalizer_set(self):
        expected = {chr(c) for c in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x180E)}
        self.assertEqual(set(detect.FOLD_CHARS), expected)


class TestMessages(unittest.TestCase):
    def test_disclosure_phrase_and_verb(self):
        self.assertEqual({h.cls for h in detect.find_message("anonymize the fixtures")}, {"disclosure"})
        self.assertEqual({h.cls for h in detect.find_message("scrub the docs")}, {"disclosure"})

    def test_harmless_collocations_pass(self):
        for msg in ("fix a memory leak in the reader", "sanitize user input in the form",
                    "expose the port for the daemon", "sanitize: one engine for copies",
                    "sanitize.py imports its tables from detect.py"):
            self.assertEqual(detect.find_message(msg), [], msg)

    def test_identifiers_in_a_message(self):
        found = {h.cls for h in detect.find_message("touch Quorvex-OKF for STORY-" + "583920",
                                                    {"zorbulate"})}
        self.assertEqual(found, {"project_folder", "work_item"})


class TestSeverity(unittest.TestCase):
    def hit(self, cls, rule="shape"):
        return detect.Hit(0, 1, cls, rule)

    def test_gate(self):
        self.assertEqual(detect.severity("gate", self.hit("secret")), "block")
        self.assertEqual(detect.severity("gate", self.hit("term")), "warn")
        self.assertEqual(detect.severity("gate", self.hit("home_path")), "block")
        self.assertEqual(detect.severity("gate", self.hit("invisible", "bidi-override")), "block")
        self.assertEqual(detect.severity("gate", self.hit("invisible", "exotic-space")), "warn")
        self.assertEqual(detect.severity("gate", self.hit("disclosure")), "block")

    def test_review(self):
        self.assertEqual(detect.severity("review", self.hit("term"), "skills/x/SKILL.md"), "block")
        self.assertEqual(detect.severity("review", self.hit("term"), "tasks/plan.md"), "warn")
        self.assertEqual(detect.severity("review", self.hit("invisible", "variation-selector")), "warn")
        self.assertIsNone(detect.severity("review", self.hit("invisible", "exotic-space")))
        self.assertIsNone(detect.severity("review", self.hit("guid")))

    def test_mail(self):
        self.assertIsNone(detect.severity("mail", self.hit("home_path")))
        self.assertIsNone(detect.severity("mail", self.hit("guid")))
        self.assertEqual(detect.severity("mail", self.hit("work_item")), "block")
        self.assertEqual(detect.severity("mail", self.hit("invisible", "tag-smuggling")), "block")


if __name__ == "__main__":
    unittest.main()
