#!/usr/bin/env python3
"""Unit + idempotency tests for ledger.py.

The engine is stdlib-only, so these run with a plain `python3 -m unittest`.

ledger.py resolves its data paths at import time from the module location, so
every test redirects those module constants at a temporary directory. Nothing
here touches the real catalog. The module also accumulates queued conflicts in
a global, so each test clears it to keep cases independent.
"""
import datetime
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ledger


class LedgerCase(unittest.TestCase):
    """Redirects ledger's data files into a scratch directory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        ledger.CATALOG = root / "catalog.tsv"
        ledger.RULES = root / "rules.tsv"
        ledger.SEED = root / "seed-sections.tsv"
        ledger.LEDGER_MD = root / "link-ledger.md"
        ledger.CONFLICTS = root / "_conflicts.tsv"
        ledger.FIELD_NOTES = root / "field-notes.tsv"
        ledger.FIELD_NOTES_MD = root / "field-notes.md"
        ledger.DECISIONS = root / "stack-decisions.tsv"
        ledger.STACK_MAP = root / "agent-stack-map.md"
        ledger._PENDING.clear()
        self.root = root

    def tearDown(self):
        ledger._PENDING.clear()
        self.tmp.cleanup()

    def write_rules(self, text):
        ledger.RULES.write_text(text)

    def write_seed(self, text):
        ledger.SEED.write_text(text)

    def run_cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ledger.main(list(argv))
        return buf.getvalue()


class RedirectionGuardTests(LedgerCase):
    """Every module-level data path must be redirected into the scratch directory.
    A path added to ledger.py but not to setUp would silently write to the real
    resources directory during a test run, which is how this suite once polluted
    the corpus with fixture rows."""

    # Directory anchors resolved at import. Nothing reads or writes them
    # directly; they only build the data paths, so they stay pointed at the repo.
    ANCHORS = {"HERE", "RES"}

    def test_no_module_path_escapes_the_scratch_directory(self):
        escaped = []
        for name in dir(ledger):
            value = getattr(ledger, name)
            if isinstance(value, Path) and name.isupper() and name not in self.ANCHORS:
                if self.root not in value.parents:
                    escaped.append(f"{name}={value}")
        self.assertEqual(
            escaped, [],
            "these ledger paths are not redirected in LedgerCase.setUp: "
            + ", ".join(escaped),
        )


class CanonTests(unittest.TestCase):
    def test_strips_fragment_and_trailing_punctuation(self):
        self.assertEqual(ledger.canon("https://x.dev/a#frag"), "https://x.dev/a")
        self.assertEqual(ledger.canon("https://x.dev/a."), "https://x.dev/a")
        self.assertEqual(ledger.canon("https://x.dev/a,"), "https://x.dev/a")

    def test_strips_trailing_slash_but_keeps_bare_root(self):
        self.assertEqual(ledger.canon("https://x.dev/a/"), "https://x.dev/a")
        self.assertEqual(ledger.canon("https://x.dev/"), "https://x.dev/")

    def test_lowercases_scheme_and_host_only(self):
        self.assertEqual(
            ledger.canon("HTTPS://GitHub.com/Owner/Repo"),
            "https://github.com/Owner/Repo",
        )

    def test_variants_collapse_to_one_key(self):
        forms = [
            "https://github.com/a/b",
            "https://github.com/a/b/",
            "https://github.com/a/b#readme",
            "https://GITHUB.com/a/b",
        ]
        self.assertEqual(len({ledger.canon(f) for f in forms}), 1)

    def test_non_url_passes_through(self):
        self.assertEqual(ledger.canon("not a url"), "not a url")


class HostRepoTests(unittest.TestCase):
    def test_extracts_github_and_deepwiki(self):
        self.assertEqual(
            ledger.host_repo("https://github.com/a/b"), ("github", "a/b")
        )
        self.assertEqual(
            ledger.host_repo("https://deepwiki.com/a/b"), ("deepwiki", "a/b")
        )

    def test_ignores_deeper_paths_beyond_owner_repo(self):
        self.assertEqual(
            ledger.host_repo("https://github.com/a/b/tree/main"), ("github", "a/b")
        )

    def test_other_hosts_return_none(self):
        self.assertEqual(ledger.host_repo("https://example.com/a/b"), (None, None))


class UnionSectionsTests(unittest.TestCase):
    def test_dedupes_and_preserves_first_seen_order(self):
        self.assertEqual(ledger.union_sections("b|a", "a|c"), "b|a|c")

    def test_handles_empty_operands(self):
        self.assertEqual(ledger.union_sections("", "a"), "a")
        self.assertEqual(ledger.union_sections("a", ""), "a")

    def test_is_stable_when_reapplied(self):
        once = ledger.union_sections("a|b", "c")
        self.assertEqual(ledger.union_sections(once, "c"), once)


class ClassifyTests(LedgerCase):
    def setUp(self):
        super().setUp()
        self.rules = [("docs.example.com", "docs"), ("re:/papers/", "papers")]
        self.seed = {"a/b": "frameworks|map"}

    def test_seed_repo_wins_over_rules(self):
        self.assertEqual(
            ledger.classify("https://github.com/a/b", self.rules, self.seed),
            "frameworks|map",
        )

    def test_deepwiki_inherits_repo_sections_and_adds_tag(self):
        self.assertEqual(
            ledger.classify("https://deepwiki.com/a/b", self.rules, self.seed),
            "frameworks|map|deepwiki",
        )

    def test_substring_and_regex_rules_match(self):
        self.assertEqual(
            ledger.classify("https://docs.example.com/x", self.rules, self.seed), "docs"
        )
        self.assertEqual(
            ledger.classify("https://z.dev/papers/1", self.rules, self.seed), "papers"
        )

    def test_first_matching_rule_wins(self):
        rules = [("example.com", "first"), ("docs.example.com", "second")]
        self.assertEqual(
            ledger.classify("https://docs.example.com/x", rules, {}), "first"
        )

    def test_unknown_repo_goes_to_triage(self):
        self.assertEqual(
            ledger.classify("https://github.com/x/y", self.rules, {}), "triage"
        )

    def test_unknown_deepwiki_repo_is_triage_plus_deepwiki(self):
        self.assertEqual(
            ledger.classify("https://deepwiki.com/x/y", self.rules, {}),
            "triage|deepwiki",
        )

    def test_unmatched_non_repo_url_is_adjacent(self):
        self.assertEqual(ledger.classify("https://z.dev/a", self.rules, {}), "adjacent")


class ExtractUrlsTests(unittest.TestCase):
    def test_dedupes_by_canonical_form_and_keeps_order(self):
        text = "see https://x.dev/b and https://x.dev/a/ and https://x.dev/a#f"
        self.assertEqual(
            ledger.extract_urls(text), ["https://x.dev/b", "https://x.dev/a"]
        )

    def test_stops_at_markdown_and_quote_delimiters(self):
        self.assertEqual(
            ledger.extract_urls("[x](https://x.dev/a) `https://x.dev/b`"),
            ["https://x.dev/a", "https://x.dev/b"],
        )


class UpsertTests(LedgerCase):
    def setUp(self):
        super().setUp()
        self.rules = [("docs.example.com", "docs")]
        self.seed = {"a/b": "frameworks"}

    def test_new_url_is_added_with_today_and_no_last_checked(self):
        rows = {}
        result = ledger.upsert(
            rows, "https://github.com/a/b", "test", self.rules, self.seed
        )
        self.assertEqual(result, "added")
        row = rows["https://github.com/a/b"]
        self.assertEqual(row["sections"], "frameworks")
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["added"], ledger.TODAY)
        self.assertEqual(row["last_checked"], "")

    def test_triage_classification_sets_triage_status(self):
        rows = {}
        ledger.upsert(rows, "https://github.com/x/y", "test", self.rules, {})
        self.assertEqual(rows["https://github.com/x/y"]["status"], "triage")

    def test_reingesting_identical_url_is_unchanged(self):
        rows = {}
        ledger.upsert(rows, "https://github.com/a/b", "test", self.rules, self.seed)
        result = ledger.upsert(
            rows, "https://github.com/a/b", "test", self.rules, self.seed
        )
        self.assertEqual(result, "unchanged")
        self.assertEqual(ledger._PENDING, [])

    def test_url_variant_does_not_create_a_second_row(self):
        rows = {}
        ledger.upsert(rows, "https://github.com/a/b", "test", self.rules, self.seed)
        ledger.upsert(rows, "https://github.com/a/b/", "test", self.rules, self.seed)
        self.assertEqual(len(rows), 1)

    def test_new_sections_union_and_log_a_conflict(self):
        rows = {}
        ledger.upsert(rows, "https://github.com/a/b", "test", self.rules, self.seed)
        result = ledger.upsert(
            rows, "https://github.com/a/b", "test", self.rules, {"a/b": "memory"}
        )
        self.assertEqual(result, "updated")
        self.assertEqual(rows["https://github.com/a/b"]["sections"], "frameworks|memory")
        self.assertEqual(ledger._PENDING[0][1], "tag-union")

    def test_curating_a_new_url_adds_it_already_flagged_manual(self):
        rows = {}
        result = ledger.upsert(
            rows,
            "https://github.com/a/b",
            "manual",
            self.rules,
            self.seed,
            manual_sections="memory|map",
        )
        self.assertEqual(result, "added")
        self.assertEqual(rows["https://github.com/a/b"]["note"], "manual")
        self.assertEqual(rows["https://github.com/a/b"]["sections"], "memory|map")

    def test_curating_an_existing_url_overrides_and_logs_a_conflict(self):
        rows = {}
        ledger.upsert(rows, "https://github.com/a/b", "test", self.rules, self.seed)
        result = ledger.upsert(
            rows,
            "https://github.com/a/b",
            "manual",
            self.rules,
            self.seed,
            manual_sections="memory|map",
        )
        self.assertEqual(result, "curated")
        self.assertEqual(rows["https://github.com/a/b"]["sections"], "memory|map")
        self.assertEqual(ledger._PENDING[-1][1], "manual-override")

    def test_manual_row_survives_a_later_automatic_ingest(self):
        rows = {}
        ledger.upsert(
            rows,
            "https://github.com/a/b",
            "manual",
            self.rules,
            self.seed,
            manual_sections="memory",
        )
        result = ledger.upsert(
            rows, "https://github.com/a/b", "test", self.rules, self.seed
        )
        self.assertEqual(result, "kept-manual")
        self.assertEqual(rows["https://github.com/a/b"]["sections"], "memory")
        self.assertEqual(ledger._PENDING[-1][1], "kept-manual")


class ConflictLedgerTests(LedgerCase):
    def test_new_conflict_is_written_hot(self):
        ledger.record_conflict("https://x.dev/a", "tag-union", "a -> b")
        new, superseded = ledger.flush_conflicts()
        self.assertEqual((new, superseded), (1, 0))
        rows = ledger.load_conflicts()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["state"], "hot")

    def test_identical_reconflict_is_a_noop(self):
        for _ in range(2):
            ledger.record_conflict("https://x.dev/a", "tag-union", "a -> b")
            ledger.flush_conflicts()
        rows = ledger.load_conflicts()
        self.assertEqual(len(rows), 1, "an identical re-conflict must not re-log")

    def test_different_conflict_supersedes_prior_hot(self):
        ledger.record_conflict("https://x.dev/a", "tag-union", "a -> b")
        ledger.flush_conflicts()
        ledger.record_conflict("https://x.dev/a", "tag-union", "b -> c")
        new, superseded = ledger.flush_conflicts()
        self.assertEqual((new, superseded), (1, 1))
        rows = ledger.load_conflicts()
        self.assertEqual([r["state"] for r in sorted(rows, key=lambda r: int(r["seq"]))],
                         ["cold", "hot"])

    def test_exactly_one_hot_row_per_url(self):
        for resolution in ("a -> b", "b -> c", "c -> d"):
            ledger.record_conflict("https://x.dev/a", "tag-union", resolution)
            ledger.flush_conflicts()
        hot = [r for r in ledger.load_conflicts() if r["state"] == "hot"]
        self.assertEqual(len(hot), 1)

    def test_flush_with_nothing_queued_is_a_noop(self):
        self.assertEqual(ledger.flush_conflicts(), (0, 0))

    def test_seq_is_monotonic_across_flushes(self):
        ledger.record_conflict("https://x.dev/a", "k", "r1")
        ledger.flush_conflicts()
        ledger.record_conflict("https://x.dev/b", "k", "r2")
        ledger.flush_conflicts()
        seqs = sorted(int(r["seq"]) for r in ledger.load_conflicts())
        self.assertEqual(seqs, [1, 2])


class StalenessTests(unittest.TestCase):
    def test_never_checked_is_stale(self):
        self.assertTrue(ledger._is_stale({"last_checked": ""}, 90))

    def test_unparseable_date_is_stale(self):
        self.assertTrue(ledger._is_stale({"last_checked": "not-a-date"}, 90))

    def test_recent_check_is_fresh_and_old_check_is_stale(self):
        recent = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()
        old = (datetime.date.today() - datetime.timedelta(days=200)).isoformat()
        self.assertFalse(ledger._is_stale({"last_checked": recent}, 90))
        self.assertTrue(ledger._is_stale({"last_checked": old}, 90))

    def test_boundary_day_is_not_yet_stale(self):
        edge = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
        self.assertFalse(ledger._is_stale({"last_checked": edge}, 90))


class RoundTripTests(LedgerCase):
    def setUp(self):
        super().setUp()
        self.write_rules("# c\ndocs.example.com\tdocs\n")
        self.write_seed("# c\na/b\tframeworks|map\n")

    def test_catalog_survives_a_save_load_cycle(self):
        rows = {}
        ledger.upsert(rows, "https://github.com/a/b", "test",
                      ledger.load_rules(), ledger.load_seed())
        ledger.save_catalog(rows)
        self.assertEqual(ledger.load_catalog(), rows)

    def test_catalog_is_written_in_canonical_url_order(self):
        rows = {}
        for u in ("https://x.dev/c", "https://x.dev/a", "https://x.dev/b"):
            ledger.upsert(rows, u, "test", [], {})
        ledger.save_catalog(rows)
        urls = [line.split("\t")[0]
                for line in ledger.CATALOG.read_text().splitlines()[1:]]
        self.assertEqual(urls, sorted(urls))

    def test_ingest_then_reingest_reports_unchanged(self):
        first = self.run_cli("ingest", "https://github.com/a/b")
        self.assertIn("added=1", first)
        second = self.run_cli("ingest", "https://github.com/a/b")
        self.assertIn("unchanged=1", second)

    def test_render_is_idempotent(self):
        self.run_cli("ingest", "https://github.com/a/b", "https://docs.example.com/x")
        self.run_cli("render")
        once = ledger.LEDGER_MD.read_text()
        self.run_cli("render")
        self.assertEqual(once, ledger.LEDGER_MD.read_text())

    def test_render_lists_every_catalog_row(self):
        self.run_cli("ingest", "https://github.com/a/b", "https://docs.example.com/x")
        self.run_cli("render")
        body = ledger.LEDGER_MD.read_text()
        self.assertIn("https://github.com/a/b", body)
        self.assertIn("https://docs.example.com/x", body)
        self.assertIn("Count: 2 URLs", body)

    def test_check_without_probe_reports_stale_rows_and_writes_nothing(self):
        self.run_cli("ingest", "https://github.com/a/b")
        before = ledger.CATALOG.read_text()
        out = self.run_cli("check", "--ttl", "90")
        self.assertIn("1 stale/unchecked", out)
        self.assertEqual(before, ledger.CATALOG.read_text())

    def test_set_curates_through_the_cli(self):
        self.run_cli("ingest", "https://github.com/a/b")
        self.run_cli("set", "https://github.com/a/b", "--sections", "memory|map")
        row = ledger.load_catalog()["https://github.com/a/b"]
        self.assertEqual(row["sections"], "memory|map")
        self.assertEqual(row["note"], "manual")

    def test_seed_scans_urls_out_of_a_markdown_bundle(self):
        src = self.root / "bundle.md"
        src.write_text("- [a](https://github.com/a/b)\n- https://docs.example.com/x\n")
        out = self.run_cli("seed", "--from-md", str(src))
        self.assertIn("added=2", out)


class FieldNoteTests(LedgerCase):
    """Unit level: the store's validation and append-only guarantee."""

    def setUp(self):
        super().setUp()
        self.write_rules("")
        self.write_seed("a/b\tframeworks\n")
        rows = {}
        ledger.upsert(rows, "https://github.com/a/b", "test", [], {"a/b": "frameworks"})
        ledger.save_catalog(rows)

    def test_note_is_stored_with_todays_date(self):
        row = ledger.add_field_note(
            "https://github.com/a/b", "broken", "segfaults on an empty index"
        )
        self.assertEqual(row["date"], ledger.TODAY)
        self.assertEqual(ledger.load_field_notes()[0]["finding"],
                         "segfaults on an empty index")

    def test_unknown_verdict_is_rejected(self):
        with self.assertRaises(ValueError) as cm:
            ledger.add_field_note("https://github.com/a/b", "sketchy", "x")
        self.assertIn("unknown verdict", str(cm.exception))
        self.assertEqual(ledger.load_field_notes(), [])

    def test_url_absent_from_catalog_is_rejected(self):
        with self.assertRaises(ValueError) as cm:
            ledger.add_field_note("https://github.com/x/y", "works", "fine")
        self.assertIn("not in the catalog", str(cm.exception))
        self.assertEqual(ledger.load_field_notes(), [])

    def test_empty_finding_is_rejected(self):
        with self.assertRaises(ValueError):
            ledger.add_field_note("https://github.com/a/b", "works", "   ")

    def test_url_is_canonicalized_before_storage(self):
        row = ledger.add_field_note("https://github.com/a/b/#readme", "works", "ok")
        self.assertEqual(row["url"], "https://github.com/a/b")

    def test_contradicting_notes_both_survive(self):
        ledger.add_field_note("https://github.com/a/b", "broken", "fails at v0.3",
                              date="2026-01-01")
        ledger.add_field_note("https://github.com/a/b", "works", "fixed by v1.0",
                              date="2026-06-01")
        notes = ledger.load_field_notes()
        self.assertEqual(len(notes), 2)
        self.assertEqual({n["verdict"] for n in notes}, {"broken", "works"})

    def test_repeated_identical_notes_are_not_deduped(self):
        for _ in range(2):
            ledger.add_field_note("https://github.com/a/b", "caution", "flaky")
        self.assertEqual(len(ledger.load_field_notes()), 2,
                         "two observations of the same thing are two observations")

    def test_store_survives_a_save_load_cycle(self):
        ledger.add_field_note("https://github.com/a/b", "works", "fine", scope="v1.2",
                              evidence="abc123")
        before = ledger.load_field_notes()
        ledger.save_field_notes(before)
        self.assertEqual(ledger.load_field_notes(), before)


class FieldNoteCliTests(LedgerCase):
    """End-to-end: drive the real CLI the way a user does."""

    def setUp(self):
        super().setUp()
        self.write_rules("")
        self.write_seed("a/b\tframeworks\n")
        self.run_cli("ingest", "https://github.com/a/b")

    def test_cli_records_and_reads_back_a_note(self):
        self.run_cli("field-note", "https://github.com/a/b", "--verdict", "broken",
                     "--finding", "OOMs above 50k documents", "--scope", "v1.2, 16GB")
        out = self.run_cli("field-notes")
        self.assertIn("OOMs above 50k documents", out)
        self.assertIn("v1.2, 16GB", out)

    def test_cli_filters_by_verdict(self):
        self.run_cli("field-note", "https://github.com/a/b", "--verdict", "works",
                     "--finding", "clean install")
        self.run_cli("field-note", "https://github.com/a/b", "--verdict", "broken",
                     "--finding", "breaks on reload")
        out = self.run_cli("field-notes", "--verdict", "broken")
        self.assertIn("breaks on reload", out)
        self.assertNotIn("clean install", out)

    def test_cli_rejects_an_uncatalogued_url(self):
        with self.assertRaises(ValueError):
            self.run_cli("field-note", "https://github.com/x/y", "--verdict", "works",
                         "--finding", "nope")

    def test_cli_rejects_an_invalid_verdict_at_parse_time(self):
        with self.assertRaises(SystemExit):
            self.run_cli("field-note", "https://github.com/a/b", "--verdict", "bogus",
                         "--finding", "x")

    def test_render_notes_is_idempotent(self):
        self.run_cli("field-note", "https://github.com/a/b", "--verdict", "caution",
                     "--finding", "needs a pinned version")
        self.run_cli("render-notes")
        once = ledger.FIELD_NOTES_MD.read_text()
        self.run_cli("render-notes")
        self.assertEqual(once, ledger.FIELD_NOTES_MD.read_text())

    def test_render_notes_puts_the_newest_note_first(self):
        ledger.add_field_note("https://github.com/a/b", "broken", "old problem",
                              date="2026-01-01")
        ledger.add_field_note("https://github.com/a/b", "works", "now fine",
                              date="2026-06-01")
        self.run_cli("render-notes")
        body = ledger.FIELD_NOTES_MD.read_text()
        self.assertLess(body.index("now fine"), body.index("old problem"))

    def test_render_notes_with_no_notes_still_writes_a_view(self):
        self.run_cli("render-notes")
        self.assertIn("Count: 0 notes", ledger.FIELD_NOTES_MD.read_text())


class ClaimsFreshnessTests(LedgerCase):
    """Claims freshness is a different axis from liveness: a URL can resolve
    while everything the map says about it has gone stale."""

    def setUp(self):
        super().setUp()
        self.write_rules("")
        self.write_seed("a/b\tframeworks|map\nc/d\tmemory|map\ne/f\tframeworks\n")
        for u in ("https://github.com/a/b", "https://github.com/c/d",
                  "https://github.com/e/f"):
            self.run_cli("ingest", u)

    def test_queue_covers_only_map_tagged_rows(self):
        out = self.run_cli("check", "--claims", "--ttl", "90")
        self.assertIn("2 map rows", out)
        self.assertIn("https://github.com/a/b", out)
        self.assertNotIn("https://github.com/e/f", out)

    def test_section_narrows_the_queue(self):
        out = self.run_cli("check", "--claims", "--section", "memory")
        self.assertIn("https://github.com/c/d", out)
        self.assertNotIn("https://github.com/a/b", out)

    def test_verified_stamps_and_drops_the_row_from_the_queue(self):
        self.run_cli("verified", "https://github.com/a/b")
        row = ledger.load_catalog()["https://github.com/a/b"]
        self.assertEqual(row["claims_checked"], ledger.TODAY)
        out = self.run_cli("check", "--claims", "--ttl", "90")
        self.assertNotIn("https://github.com/a/b", out)
        self.assertIn("https://github.com/c/d", out)

    def test_verified_reports_an_uncatalogued_url_instead_of_adding_it(self):
        out = self.run_cli("verified", "https://github.com/x/y")
        self.assertIn("NOT IN CATALOG", out)
        self.assertNotIn("https://github.com/x/y", ledger.load_catalog())

    def test_liveness_and_claims_are_independent(self):
        catalog = ledger.load_catalog()
        catalog["https://github.com/a/b"]["last_checked"] = ledger.TODAY
        ledger.save_catalog(catalog)
        out = self.run_cli("check", "--claims", "--ttl", "90")
        self.assertIn("https://github.com/a/b", out,
                      "a fresh liveness probe must not mark claims as verified")

    def test_claims_go_stale_again_after_the_ttl(self):
        catalog = ledger.load_catalog()
        old = (datetime.date.today() - datetime.timedelta(days=200)).isoformat()
        catalog["https://github.com/a/b"]["claims_checked"] = old
        ledger.save_catalog(catalog)
        self.assertIn("https://github.com/a/b",
                      self.run_cli("check", "--claims", "--ttl", "90"))


class TagNormalizationTests(LedgerCase):
    def test_map_tag_is_a_discrete_tag_not_a_suffix(self):
        self.write_rules("")
        self.write_seed("a/b\tframeworks|map\n")
        self.run_cli("ingest", "https://github.com/a/b")
        sections = ledger.load_catalog()["https://github.com/a/b"]["sections"]
        self.assertIn("map", sections.split("|"))
        self.assertNotIn("(map)", sections)


class MapTagDerivationTests(LedgerCase):
    """The `map` tag means the URL has a row in agent-stack-map.md. Hand-
    maintained it drifts in both directions, so it is derived."""

    def setUp(self):
        super().setUp()
        self.write_rules("")
        self.write_seed("")
        self.map_md = ledger.STACK_MAP
        for u in ("https://github.com/a/b", "https://github.com/c/d"):
            self.run_cli("ingest", u)

    def write_map(self, *urls):
        body = "\n".join(f"| Tool | [repo]({u}) |" for u in urls)
        self.map_md.write_text("# map\n\n" + body + "\n")

    def test_tag_is_added_to_rows_present_in_the_map(self):
        self.write_map("https://github.com/a/b")
        self.run_cli("sync-map-tags")
        self.assertIn("map",
                      ledger.load_catalog()["https://github.com/a/b"]["sections"].split("|"))

    def test_stale_tag_is_removed_when_the_row_left_the_map(self):
        self.run_cli("set", "https://github.com/c/d", "--sections", "memory|map")
        self.write_map("https://github.com/a/b")
        self.run_cli("sync-map-tags")
        sections = ledger.load_catalog()["https://github.com/c/d"]["sections"].split("|")
        self.assertNotIn("map", sections)
        self.assertIn("memory", sections, "only the map tag is derived; others survive")

    def test_running_twice_changes_nothing_the_second_time(self):
        self.write_map("https://github.com/a/b")
        self.run_cli("sync-map-tags")
        before = ledger.CATALOG.read_text()
        out = self.run_cli("sync-map-tags")
        self.assertIn("+0 tagged, -0 untagged", out)
        self.assertEqual(before, ledger.CATALOG.read_text())

    def test_map_url_missing_from_the_catalog_is_reported(self):
        self.write_map("https://github.com/a/b", "https://github.com/never/ingested")
        out = self.run_cli("sync-map-tags")
        self.assertIn("not in the catalog", out)
        self.assertIn("https://github.com/never/ingested", out)

    def test_url_variants_in_the_map_still_match_the_catalog_row(self):
        self.write_map("https://github.com/a/b/")
        self.run_cli("sync-map-tags")
        self.assertIn("map",
                      ledger.load_catalog()["https://github.com/a/b"]["sections"].split("|"))


class StackDecisionTests(LedgerCase):
    SHAPE = "local-first single-user coding agent"

    def setUp(self):
        super().setUp()
        self.write_rules("")
        self.write_seed("a/b\tframeworks\n")
        rows = {}
        ledger.upsert(rows, "https://github.com/a/b", "test", [], {"a/b": "frameworks"})
        ledger.save_catalog(rows)

    def test_decision_starts_with_an_empty_outcome(self):
        row = ledger.add_decision(self.SHAPE, "memory", "https://github.com/a/b",
                                  "no hosted control plane")
        self.assertEqual(row["outcome"], "")
        self.assertEqual(row["use_case"], self.SHAPE)

    def test_uncatalogued_component_is_rejected(self):
        with self.assertRaises(ValueError) as cm:
            ledger.add_decision(self.SHAPE, "memory", "https://github.com/x/y", "r")
        self.assertIn("not in the catalog", str(cm.exception))

    def test_blank_shape_or_layer_is_rejected(self):
        with self.assertRaises(ValueError):
            ledger.add_decision("  ", "memory", "https://github.com/a/b", "r")
        with self.assertRaises(ValueError):
            ledger.add_decision(self.SHAPE, " ", "https://github.com/a/b", "r")

    def test_outcome_stamps_the_open_decision(self):
        ledger.add_decision(self.SHAPE, "memory", "https://github.com/a/b", "r")
        stamped = ledger.stamp_outcome(self.SHAPE, "memory", "held")
        self.assertEqual(stamped["outcome"], "held")
        self.assertEqual(ledger.load_decisions()[0]["outcome"], "held")

    def test_stamping_with_nothing_open_returns_none(self):
        self.assertIsNone(ledger.stamp_outcome(self.SHAPE, "memory", "held"))

    def test_stamping_twice_leaves_the_first_outcome_alone(self):
        ledger.add_decision(self.SHAPE, "memory", "https://github.com/a/b", "r",
                            date="2026-01-01")
        ledger.stamp_outcome(self.SHAPE, "memory", "held")
        self.assertIsNone(ledger.stamp_outcome(self.SHAPE, "memory", "replaced"))
        self.assertEqual(ledger.load_decisions()[0]["outcome"], "held")

    def test_newest_open_decision_is_the_one_stamped(self):
        ledger.add_decision(self.SHAPE, "memory", "https://github.com/a/b", "old",
                            date="2026-01-01")
        ledger.add_decision(self.SHAPE, "memory", "https://github.com/a/b", "new",
                            date="2026-06-01")
        stamped = ledger.stamp_outcome(self.SHAPE, "memory", "replaced")
        self.assertEqual(stamped["date"], "2026-06-01")
        still_open = [r for r in ledger.load_decisions() if not r["outcome"]]
        self.assertEqual(len(still_open), 1)

    def test_unknown_outcome_is_rejected(self):
        with self.assertRaises(ValueError):
            ledger.stamp_outcome(self.SHAPE, "memory", "vibes")

    def test_decisions_for_different_layers_are_independent(self):
        ledger.add_decision(self.SHAPE, "memory", "https://github.com/a/b", "r")
        ledger.add_decision(self.SHAPE, "retrieval", "https://github.com/a/b", "r")
        ledger.stamp_outcome(self.SHAPE, "memory", "held")
        open_rows = [r for r in ledger.load_decisions() if not r["outcome"]]
        self.assertEqual([r["layer"] for r in open_rows], ["retrieval"])


class StackDecisionCliTests(LedgerCase):
    SHAPE = "batch document extraction, no UI"

    def setUp(self):
        super().setUp()
        self.write_rules("")
        self.write_seed("a/b\tframeworks\n")
        self.run_cli("ingest", "https://github.com/a/b")

    def test_cli_records_and_queries_a_decision(self):
        self.run_cli("decision", "--use-case", self.SHAPE, "--layer", "ingestion",
                     "--component", "https://github.com/a/b",
                     "--rationale", "AGPL incompatible with the license")
        out = self.run_cli("decisions")
        self.assertIn(self.SHAPE, out)
        self.assertIn("AGPL incompatible", out)
        self.assertIn("[open]", out)

    def test_cli_stamps_an_outcome_and_it_leaves_the_open_list(self):
        self.run_cli("decision", "--use-case", self.SHAPE, "--layer", "ingestion",
                     "--component", "https://github.com/a/b", "--rationale", "r")
        self.assertIn("ingestion", self.run_cli("decisions", "--open"))
        self.run_cli("outcome", "--use-case", self.SHAPE, "--layer", "ingestion",
                     "--outcome", "replaced")
        self.assertNotIn("ingestion", self.run_cli("decisions", "--open"))

    def test_cli_query_filters_by_shape(self):
        self.run_cli("decision", "--use-case", self.SHAPE, "--layer", "ingestion",
                     "--component", "https://github.com/a/b", "--rationale", "r")
        self.run_cli("decision", "--use-case", "something else entirely",
                     "--layer", "memory", "--component", "https://github.com/a/b",
                     "--rationale", "r")
        out = self.run_cli("decisions", "batch document")
        self.assertIn("ingestion", out)
        self.assertNotIn("something else", out)

    def test_cli_reports_when_there_is_nothing_open_to_stamp(self):
        out = self.run_cli("outcome", "--use-case", self.SHAPE, "--layer", "memory",
                           "--outcome", "held")
        self.assertIn("no open decision", out)


class ConflictPruneTests(LedgerCase):
    def test_prune_drops_only_aged_cold_rows(self):
        old = (datetime.date.today() - datetime.timedelta(days=200)).isoformat()
        ledger.save_conflicts([
            dict(seq="1", date=old, url="https://x.dev/a", kind="k",
                 resolution="r", state="cold"),
            dict(seq="2", date=ledger.TODAY, url="https://x.dev/a", kind="k",
                 resolution="r2", state="hot"),
            dict(seq="3", date=ledger.TODAY, url="https://x.dev/b", kind="k",
                 resolution="r3", state="cold"),
        ])
        self.run_cli("conflicts", "--prune", "--ttl", "90")
        remaining = ledger.load_conflicts()
        self.assertEqual({r["seq"] for r in remaining}, {"2", "3"})


if __name__ == "__main__":
    unittest.main()
