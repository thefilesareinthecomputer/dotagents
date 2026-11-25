"""Tests for kg_core, the code both knowledge-graph engines import. Each
engine's own suite covers how it uses these through its commands; this one
covers the functions themselves.

Run: python3 -m unittest discover -s lib/tests
"""
import contextlib
import heapq
import io
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kg_core  # noqa: E402

# Creating a symlink on Windows needs Developer Mode or admin rights.
needs_symlinks = unittest.skipIf(sys.platform == "win32",
                                 "symlinks need Developer Mode or admin rights on Windows")


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kgcore-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class LegacyFolderRowTests(unittest.TestCase):
    LEGACY = {"vault-kg": {}, "markdown-kg": {}}

    def test_the_folders_own_forms_match(self):
        for row in ("vault-kg", "./vault-kg", "/vault-kg/**/", "vault-kg/*/*",
                    "//vault-kg//", " markdown-kg/** "):
            self.assertTrue(kg_core.legacy_folder_row(row, self.LEGACY), row)

    def test_a_pattern_that_only_mentions_the_name_is_kept(self):
        for row in ("vault-kg-notes/", "docs/vault-kg/", "vault-kg.md", "**/vault-kg/",
                    "vault-kg/*.db", "vault-kg/**/*.md", "!vault-kg/", "./../vault-kg"):
            self.assertFalse(kg_core.legacy_folder_row(row, self.LEGACY), row)

    def test_a_hostile_row_is_judged_in_linear_time(self):
        started = time.monotonic()
        for row in ("/*" * 500000 + "x", "vault-kg" + "/*" * 500000 + "x"):
            self.assertFalse(kg_core.legacy_folder_row(row, self.LEGACY))
        self.assertLess(time.monotonic() - started, 1.0)


class SeedFolderTests(TempCase):
    def test_a_new_folder_gets_every_file(self):
        kg = self.tmp / ".kg"
        kg.mkdir()
        kg_core.seed_folder(kg)
        for name, text in kg_core.KG_FOLDER_FILES.items():
            self.assertEqual((kg / name).read_text(encoding="utf-8"), text)
        self.assertEqual((kg / "CLAUDE.md").read_text(), "@AGENTS.md\n")

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_the_gitignore_keeps_databases_out_and_configs_in(self):
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        (self.tmp / ".kg").mkdir()
        kg_core.seed_folder(self.tmp / ".kg")
        names = ["code-kg.db", "code-kg.db-wal", "code-kg.db-journal",
                 "code-kg-prev.db", "code-kg-prev.db.x1.tmp",
                 "markdown-kg.db-shm", "code-kg-config.json",
                 "markdown-kg-config.json", "README.md", "AGENTS.md",
                 "CLAUDE.md", ".gitignore"]
        got = subprocess.run(
            ["git", "-C", str(self.tmp), "check-ignore", "--no-index",
             *[f".kg/{n}" for n in names]],
            capture_output=True, text=True).stdout.split()
        self.assertEqual(got, [f".kg/{n}" for n in names[:6]])

    def test_the_old_star_seed_is_replaced_and_other_files_kept(self):
        kg = self.tmp / ".kg"
        kg.mkdir()
        (kg / ".gitignore").write_text(kg_core.OLD_GITIGNORE_SEED)
        (kg / "README.md").write_text("ours\n")
        kg_core.seed_folder(kg)
        self.assertEqual((kg / ".gitignore").read_text(),
                         kg_core.KG_FOLDER_FILES[".gitignore"])
        self.assertEqual((kg / "README.md").read_text(), "ours\n")

    def test_an_existing_gitignore_is_never_rewritten(self):
        kg = self.tmp / ".kg"
        kg.mkdir()
        (kg / ".gitignore").write_text("code-kg.db\n")
        kg_core.seed_folder(kg)
        self.assertEqual((kg / ".gitignore").read_text(), "code-kg.db\n")

    def test_a_legacy_folder_gets_only_its_gitignore(self):
        legacy = self.tmp / ".code-kg"
        legacy.mkdir()
        kg_core.seed_folder(legacy)
        self.assertEqual([p.name for p in legacy.iterdir()], [".gitignore"])

    @needs_symlinks
    def test_planted_links_at_the_seeded_names_are_not_written_through(self):
        kg = self.tmp / "repo" / ".kg"
        kg.mkdir(parents=True)
        outside = self.tmp / "outside.md"
        outside.write_text("keep\n")
        os.symlink(outside, kg / "README.md")
        os.symlink(self.tmp / "dangling.md", kg / "AGENTS.md")
        kg_core.seed_folder(kg)
        self.assertEqual(outside.read_text(), "keep\n")
        self.assertFalse((self.tmp / "dangling.md").exists())
        self.assertFalse((kg / "CLAUDE.md").exists())

    def test_a_planted_agents_md_gets_no_claude_pointer(self):
        kg = self.tmp / ".kg"
        kg.mkdir()
        (kg / "AGENTS.md").write_text("planted\n")
        kg_core.seed_folder(kg)
        self.assertEqual((kg / "AGENTS.md").read_text(), "planted\n")
        self.assertFalse((kg / "CLAUDE.md").exists())


class StoreTests(TempCase):
    @needs_symlinks
    def test_a_read_never_writes_through_a_planted_database_link(self):
        outside = self.tmp / "outside.db"
        con = sqlite3.connect(outside)
        con.execute("CREATE TABLE keep (x)")
        con.commit()
        con.close()
        root = self.tmp / "repo"
        (root / ".kg").mkdir(parents=True)
        os.symlink(outside, root / ".kg" / "code-kg.db")
        store = kg_core.Store("code-kg", "repo", legacy={})
        with self.assertRaises(SystemExit):
            store.recorded_manifest(root)
        con = sqlite3.connect(outside)
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        con.close()
        self.assertEqual(tables, ["keep"])


class GlobTests(unittest.TestCase):
    def test_semantics(self):
        for path, pattern, expected in (
            ("app/main.py", "app/*.py", True),
            ("app/sub/main.py", "app/*.py", False),
            ("a/b/c/d.py", "a/**/d.py", True),
            ("web/lib/api.ts", "web/**", True),
            ("archive/old/a.md", "archive/**", True),
            ("live/a.md", "archive/**", False),
            ("deep/journal.md", "journal.md", True),
            ("x/dist/y.js", "dist", True),
            ("a/b/thing.min.js", "*.min.js", True),
            ("a/node_modules/x.md", "node_modules", True),
            ("a/drafts/x.md", "drafts/", True),
            ("notes/x.md", "notes/", True),
            ("gen/a.md", "gen/*.md", True),
            ("gen/deep/a.md", "gen/*.md", False),
            (".obsidian/x.md", ".obsidian/**", True),
            ("obsidian/x.md", ".obsidian/**", False),
            ("a.md", "./a.md", True),
            ("abc.md", "a?c.md", True),
            ("abcd.md", "a?c.md", False),
        ):
            self.assertEqual(kg_core.glob_match(path, pattern), expected,
                             msg=f"{path} vs {pattern}")

    def test_an_overlong_pattern_is_refused(self):
        self.assertFalse(kg_core.glob_match("a", "*" * 600))

    def test_a_pathological_pattern_stays_fast(self):
        # 32s against the backtracking regex the linear matcher replaced,
        # and 72s once the pattern grew.
        for pattern, path in ((("*a" * 10) + "*b", "a" * 43 + ".md"),
                              (("*a" * 30) + "*b", "a" * 200 + ".md"),
                              ("**/" * 30 + "*b", "a/" * 40 + "x.md")):
            start = time.perf_counter()
            self.assertFalse(kg_core.glob_match(path, pattern))
            self.assertLess(time.perf_counter() - start, 0.1, msg=pattern)


class TokenizeTests(unittest.TestCase):
    def test_phrases_terms_and_stopwords(self):
        self.assertEqual(
            kg_core.tokenize('the "exact phrase" Cache cache x it\'s', {"the"}),
            (["exact phrase"], ["cache", "it's"]))


class TermSafeTests(unittest.TestCase):
    """Prose output shows every invisible or reordering character as an
    escape. Characters are built with chr() so this file holds none."""

    TAG_A, RLO, ZWSP = chr(0xE0041), chr(0x202E), chr(0x200B)
    ZWJ, VS16, ESC = chr(0x200D), chr(0xFE0F), chr(0x1B)
    safe = staticmethod(kg_core.term_safe)

    def test_plain_text_is_untouched(self):
        for text in ("Heading\twith tab\nand caf" + chr(0xE9) + ".\n",
                     "def f():\n\treturn 'caf" + chr(0xE9) + "'\n"):
            self.assertEqual(self.safe(text), text)

    def test_control_and_invisible_characters_become_visible(self):
        self.assertEqual(self.safe("a" + self.ESC + "[2Jb\rc" + chr(0x9B)),
                         "a\\x1b[2Jb\\rc\\x9b")
        for ch, shown in ((chr(0x07), "\\x07"), (self.TAG_A, "\\U000e0041"),
                          (self.RLO, "\\u202e"), (self.ZWSP, "\\u200b"),
                          (chr(0x2066), "\\u2066"), (chr(0xFEFF), "\\ufeff"),
                          (chr(0xAD), "\\xad"), (chr(0x2062), "\\u2062"),
                          (chr(0x2800), "\\u2800"), (chr(0x2028), "\\u2028"),
                          (chr(0x200E), "\\u200e"),
                          (chr(0xE0101), "\\U000e0101")):
            self.assertEqual(self.safe("x" + ch + "y"), "x" + shown + "y")

    def test_a_hidden_run_cannot_ride_inside_a_word(self):
        hidden = "".join(chr(0xE0000 + ord(c)) for c in "run this")
        got = self.safe("note" + hidden + " text")
        self.assertTrue(got.isascii())
        self.assertEqual(got.count("\\U000e00"), len("run this"))

    def test_emoji_sequences_survive_and_a_stray_joiner_does_not(self):
        technologist = chr(0x1F469) + self.ZWJ + chr(0x1F4BB)
        on_fire = chr(0x2764) + self.VS16 + self.ZWJ + chr(0x1F525)
        for text in (technologist, on_fire, chr(0x2764) + self.VS16):
            self.assertEqual(self.safe(text), text)
        self.assertEqual(self.safe("pass" + self.ZWJ + "word"),
                         "pass\\u200dword")
        self.assertEqual(self.safe(self.ZWJ + chr(0x1F525)),
                         "\\u200d" + chr(0x1F525))

    def test_variation_selectors_survive_only_where_emoji_need_them(self):
        heart, vs15, keycap = chr(0x2764), chr(0xFE0E), chr(0x20E3)
        for text in (heart + self.VS16, chr(0x263A) + vs15,
                     "1" + self.VS16 + keycap, chr(0xA9) + self.VS16):
            self.assertEqual(self.safe(text), text)
        # After a letter, and every selector past the first in a run: a run
        # of selectors after one base character is a hidden byte channel.
        self.assertEqual(self.safe("a" + self.VS16), "a\\ufe0f")
        self.assertEqual(self.safe(heart + self.VS16 + chr(0xFE01) + vs15),
                         heart + self.VS16 + "\\ufe01\\ufe0e")
        self.assertEqual(self.safe("x" + chr(0x180F)), "x\\u180f")


def reference_greedy_modularity(adj: dict, deg: dict, m: float) -> dict:
    """The clustering as first shipped: correct, and it rescans the whole
    link table on every merge. Kept here as the answer key the faster
    version must reproduce exactly."""
    if m <= 0:
        return {}
    comm = {n: i for i, n in enumerate(sorted(adj))}
    members = {i: {n} for n, i in comm.items()}
    tot = {comm[n]: deg[n] for n in adj}
    link = {}
    for a, nbrs in adj.items():
        for b, w in nbrs.items():
            ca, cb = comm[a], comm[b]
            if ca == cb:
                continue
            link[(ca, cb) if ca < cb else (cb, ca)] = w

    def gain(ca, cb):
        w = link.get((ca, cb) if ca < cb else (cb, ca), 0.0)
        return w / m - (tot[ca] * tot[cb]) / (2.0 * m * m)

    heap = [(-gain(a, b), a, b) for a, b in link]
    heapq.heapify(heap)
    while heap:
        negdq, ca, cb = heapq.heappop(heap)
        if ca not in members or cb not in members:
            continue
        if ((ca, cb) if ca < cb else (cb, ca)) not in link:
            continue
        fresh = gain(ca, cb)
        if abs(fresh - (-negdq)) > 1e-12:
            heapq.heappush(heap, (-fresh, ca, cb))
            continue
        if fresh <= 1e-12:
            break
        keep, drop = (ca, cb) if ca < cb else (cb, ca)
        members[keep] |= members.pop(drop)
        tot[keep] += tot.pop(drop)
        for n in members[keep]:
            comm[n] = keep
        for k in [k for k in link if drop in k]:
            w = link.pop(k)
            other = k[0] if k[1] == drop else k[1]
            if other == keep:
                continue
            nk = (keep, other) if keep < other else (other, keep)
            link[nk] = link.get(nk, 0.0) + w
        for k in list(link):
            if keep in k:
                other = k[0] if k[1] == keep else k[1]
                heapq.heappush(heap, (-gain(keep, other), keep, other))
    return comm


def random_graph(rng, nodes: int, edges: int):
    """Symmetric weighted adjacency in the shape both engines build."""
    names = [f"n{i:05d}" for i in range(nodes)]
    adj = {}
    for _ in range(edges):
        a, b = rng.choice(names), rng.choice(names)
        if a == b:
            continue
        w = float(rng.randint(1, 3))
        adj.setdefault(a, {})
        adj.setdefault(b, {})
        adj[a][b] = adj[a].get(b, 0.0) + w
        adj[b][a] = adj[a][b]
    deg = {n: sum(w.values()) for n, w in adj.items()}
    return adj, deg, sum(deg.values()) / 2.0


def star_graph(leaves: int):
    """One hub linked to every leaf, unit weights. The hub sorts last."""
    hub = "zz-hub"
    adj = {hub: {}}
    for i in range(leaves):
        leaf = f"leaf{i:05d}"
        adj[hub][leaf] = 1.0
        adj[leaf] = {hub: 1.0}
    deg = {n: sum(w.values()) for n, w in adj.items()}
    return adj, deg, sum(deg.values()) / 2.0


class PrintHelperTests(unittest.TestCase):
    def printed(self, *args) -> list[str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            kg_core.print_capped(*args)
        return buf.getvalue().splitlines()

    def test_a_cut_list_says_how_many_were_left_out(self):
        self.assertEqual(self.printed(["a", "b", "c"], 2),
                         ["  a", "  b", "  TRUNCATED: 1 more"])

    def test_a_negative_limit_prints_everything(self):
        # A negative slice would drop the tail while claiming a count.
        self.assertEqual(self.printed(["a", "b", "c"], -1),
                         ["  a", "  b", "  c"])

    def test_the_format_applies_to_each_item(self):
        self.assertEqual(self.printed([1, 2], 5, lambda n: f"#{n}"),
                         ["  #1", "  #2"])

    def test_the_fingerprint_survives_a_new_process(self):
        # A constant holding functions must not key the cache by address,
        # or every run starts cold.
        def ns():
            return {"TABLE": {"py": lambda: 0}, "CAP": 5, "lower": 1}
        one = kg_core.engine_fingerprint(__file__, ns())
        self.assertEqual(one, kg_core.engine_fingerprint(__file__, ns()))
        self.assertNotEqual(one, kg_core.engine_fingerprint(
            __file__, {**ns(), "CAP": 6}))

    def test_a_seal_holds_on_one_machine_only(self):
        old, saved = os.environ.get("XDG_STATE_HOME"), kg_core.ParseCache._source
        self.addCleanup(setattr, kg_core.ParseCache, "_source", saved)
        self.addCleanup(lambda: os.environ.pop("XDG_STATE_HOME", None)
                        if old is None
                        else os.environ.__setitem__("XDG_STATE_HOME", old))
        with tempfile.TemporaryDirectory() as tmp:
            seals = []
            for station in ("a", "a", "b"):
                os.environ["XDG_STATE_HOME"] = os.path.join(tmp, station)
                kg_core.ParseCache._source = None
                seals.append(kg_core.seal("basis"))
        self.assertEqual(seals[0], seals[1])
        self.assertNotEqual(seals[0], seals[2])

    def test_line_starts_index_each_line(self):
        self.assertEqual(kg_core.line_starts("ab\ncd\n"), [0, 3, 6])
        self.assertEqual(kg_core.line_starts(""), [0])


class ClusteringTests(unittest.TestCase):
    def test_same_groups_as_the_reference_on_random_graphs(self):
        rng = random.Random(20261114)
        for _ in range(400):
            nodes = rng.randint(2, 45)
            adj, deg, m = random_graph(rng, nodes, rng.randint(1, nodes * 3))
            got = kg_core.greedy_modularity(adj, deg, m)
            want = reference_greedy_modularity(adj, deg, m)
            self.assertEqual(got, want)
            self.assertEqual(list(got), list(want))

    def test_same_groups_on_stars_and_tie_heavy_graphs(self):
        """A hub every other node links to is a star, and it is where a merge
        queue that keeps its stale entries grows fastest. Unit weights make
        every gain a tie, which is where a change in the order entries leave
        the queue would show."""
        rng = random.Random(11)
        graphs = [star_graph(n) for n in (2, 3, 7, 25, 60)]
        for _ in range(150):
            nodes = rng.randint(3, 30)
            adj, deg, m = star_graph(nodes)
            names = sorted(adj)
            for _ in range(rng.randint(0, nodes)):
                a, b = rng.sample(names, 2)
                adj[a][b] = adj[b][a] = 1.0
            deg = {n: sum(w.values()) for n, w in adj.items()}
            graphs.append((adj, deg, sum(deg.values()) / 2.0))
        for adj, deg, m in graphs:
            self.assertEqual(kg_core.greedy_modularity(adj, deg, m),
                             reference_greedy_modularity(adj, deg, m))

    def test_a_star_clusters_quickly(self):
        adj, deg, m = star_graph(1000)
        start = time.time()
        got = kg_core.greedy_modularity(adj, deg, m)
        # A queue that re-queues every stale entry needs minutes here.
        self.assertLess(time.time() - start, 5.0)
        self.assertEqual(len(got), 1001)

    def test_a_large_graph_clusters_quickly(self):
        adj, deg, m = random_graph(random.Random(7), 4000, 20000)
        start = time.time()
        got = kg_core.greedy_modularity(adj, deg, m)
        # The reference needs several seconds here.
        self.assertLess(time.time() - start, 2.0)
        self.assertEqual(set(got), set(adj))

    def test_empty_graph(self):
        self.assertEqual(kg_core.greedy_modularity({}, {}, 0.0), {})


if __name__ == "__main__":
    unittest.main()
