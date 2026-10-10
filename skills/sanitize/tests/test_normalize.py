#!/usr/bin/env python3
"""Tests for normalized term matching: skills/sanitize/scripts/normalize.py and its
wiring into scrub_text. Every term is invented. The obfuscations here are the ones
arXiv:2609.03464 tests against the common scrubbers: split tokens, inserted
punctuation, confusables, zero-width characters, base64 and hex. Invisible
characters are built from codepoints so the source itself holds none.
Run: python3 -m unittest discover -s skills/sanitize/tests -v
"""

import base64
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nz = load("normalize")
sz = load("sanitize")

T = {"zorbulate"}
ZW = chr(0x200B)


class TestNormalizedView(unittest.TestCase):
    def test_drops_whitespace_punctuation_and_zero_width_and_maps_indices(self):
        text = "a b" + ZW + "-c"
        norm, idx = nz.normalized_view(text)
        self.assertEqual(norm, "abc")
        self.assertEqual([text[i] for i in idx], ["a", "b", "c"])

    def test_folds_confusables_and_fullwidth(self):
        # Cyrillic o and a, Greek epsilon, fullwidth E, dotless i
        norm, _ = nz.normalized_view("zоrbulаtε Ｅ ı")
        self.assertEqual(norm, "zorbulateEi")

    def test_nfkc_expansion_keeps_a_map_entry_per_char(self):
        text = "ﬁle"  # the fi ligature expands to two characters
        norm, idx = nz.normalized_view(text)
        self.assertEqual(norm, "file")
        self.assertEqual(idx, [0, 0, 1, 2])


class TestNormalizedTermHits(unittest.TestCase):
    def hits(self, text, terms=T):
        return nz.normalized_hits(text, terms)

    def test_split_with_spaces(self):
        self.assertEqual(self.hits("see z o r b u l a t e here"), [(4, 21)])

    def test_inserted_punctuation(self):
        self.assertEqual(self.hits("zor.bu-la.te"), [(0, 12)])

    def test_zero_width_inside(self):
        text = "zorbu" + ZW + "late"
        self.assertEqual(self.hits(text), [(0, len(text))])

    def test_substring_of_a_longer_word_is_not_a_hit(self):
        self.assertEqual(self.hits("zorbulates"), [])
        self.assertEqual(self.hits("markzorbulate"), [])

    def test_single_case_term_matches_any_case(self):
        self.assertEqual(self.hits("Z O R B U L A T E"), [(0, 17)])

    def test_mixed_case_term_matches_as_typed_only(self):
        self.assertEqual(self.hits("q u i n t a x i a", {"Quintaxia"}), [])
        self.assertEqual(self.hits("Q u i n t a x i a", {"Quintaxia"}), [(0, 17)])

    def test_terms_under_four_normalized_chars_are_skipped(self):
        self.assertEqual(self.hits("a b c", {"a b", "abc"}), [])
        self.assertEqual(self.hits("a b c d", {"abcd"}), [(0, 7)])

    def test_symbol_edged_term_normalizes_to_its_letters(self):
        self.assertEqual(self.hits("tag word", {"#tagword"}), [(0, 8)])


class TestEncodedRuns(unittest.TestCase):
    def test_base64_run_holding_a_term_is_replaced_whole(self):
        enc = base64.b64encode(b"the zorbulate file is here").decode()
        counts = {}
        out = sz.scrub_text(f"blob {enc} end", T, counts)
        self.assertEqual(out, "blob [TERM] end")
        self.assertEqual(counts, {"term-encoded": 1})

    def test_hex_run_holding_a_term_is_replaced_whole(self):
        enc = b"ask zorbulate about it".hex()
        out = sz.scrub_text(f"x {enc} y", T, {})
        self.assertEqual(out, "x [TERM] y")

    def test_base64_run_without_a_term_is_left_alone(self):
        enc = base64.b64encode(b"nothing to see in this text at all").decode()
        out = sz.scrub_text(f"blob {enc} end", T, {})
        self.assertEqual(out, f"blob {enc} end")

    def test_binary_looking_base64_is_left_alone(self):
        enc = base64.b64encode(bytes(range(0, 64))).decode()
        out = sz.scrub_text(f"blob {enc} end", T, {})
        self.assertEqual(out, f"blob {enc} end")

    def test_decoded_text_is_rescanned_once_not_recursively(self):
        inner = base64.b64encode(b"zorbulate").decode()
        outer = base64.b64encode(f"wrapped {inner} twice".encode()).decode()
        out = sz.scrub_text(f"blob {outer} end", T, {})
        self.assertEqual(out, f"blob {outer} end")


class TestScrubTextWiring(unittest.TestCase):
    def test_normalized_hit_counts_as_term(self):
        counts = {}
        out = sz.scrub_text("owner: z o r b u l a t e.", T, counts)
        self.assertEqual(out, "owner: [TERM].")
        self.assertEqual(counts, {"term-normalized": 1})

    def test_normalized_hit_on_a_ban_term_counts_as_ban(self):
        counts = {}
        out = sz.scrub_text("b l o r f", set(), counts, extra_terms={"blorf"})
        self.assertEqual(out, "[TERM]")
        self.assertEqual(counts, {"ban-normalized": 1})

    def test_raw_and_normalized_hits_are_counted_apart(self):
        counts = {}
        out = sz.scrub_text("zorbulate and z-o-r-b-u-l-a-t-e", T, counts)
        self.assertEqual(out, "[TERM] and [TERM]")
        self.assertEqual(counts, {"term": 1, "term-normalized": 1})

    def test_term_hit_sees_every_view(self):
        self.assertTrue(sz.term_hit({"term-normalized": 1}))
        self.assertTrue(sz.term_hit({"ban-encoded": 2}))
        self.assertFalse(sz.term_hit({"secret": 3, "email": 1, "term": 0}))

    def test_placeholder_is_not_rematched_by_the_normalized_view(self):
        # Council finding 2026-10-10: the raw pass wrote [TERM], the normalized view folded
        # the brackets away and matched TERM again, giving [[TERM]] and two counts.
        counts = {}
        out = sz.scrub_text("term", {"term"}, counts)
        self.assertEqual(out, "[TERM]")
        self.assertEqual(counts, {"term": 1})

    def test_raw_replacement_cannot_hide_a_split_token_hit(self):
        # Council finding 2026-10-10: with {foo, foobar}, replacing foo first left
        # "[TERM] bar", so the split-token hit on "foo bar" never fired and bar shipped.
        counts = {}
        out = sz.scrub_text("foo bar", {"foo!", "foo bar"}, counts)
        self.assertEqual(out, "[TERM]")
        self.assertEqual(counts, {"term": 1})
        counts = {}
        out = sz.scrub_text("zorb ulate", {"zorb", "zorbulate"}, counts)
        self.assertEqual(out, "[TERM]")
        self.assertEqual(counts, {"term-normalized": 1})

    def test_output_is_independent_of_term_set_order(self):
        import itertools
        results = set()
        for order in itertools.permutations(["ab cd", "cd ef", "abcd"]):
            counts = {}
            results.add((sz.scrub_text("ab cd ef", set(order), counts), tuple(sorted(counts.items()))))
        self.assertEqual(len(results), 1, results)

    def test_confusable_spelling_in_prose(self):
        out = sz.scrub_text("the zоrbulate team", T, {})
        self.assertEqual(out, "the [TERM] team")


if __name__ == "__main__":
    unittest.main()
