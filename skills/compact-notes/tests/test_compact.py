"""Tests for scripts/compact.py."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'compact.py'
sys.path.insert(0, str(SCRIPT.parent))
import compact  # noqa: E402

# Creating a symlink on Windows needs Developer Mode or admin rights.
needs_symlinks = unittest.skipIf(sys.platform == 'win32',
                                 'symlinks need Developer Mode or admin rights on Windows')

NOTE = """---
type: meeting_note
title: t
---
# T

## 2026-07-10

A long paragraph of narrative that should be compacted away eventually.
Another line of narrative padding to give the section some real weight.

### DECISIONS
- 2026-07-10 - a decision

---
## 2026-07-11-ALL
- [x] REFINED 2026-07-11 (COMPACTED 2026-07-12)

Already compacted takeaways.

### ACTIONS
- [x] done thing (owner: A; opened 2026-07-11; resolved 2026-07-11 - done)

---
## 2026-07-12-OLD
- [x] REFINED 2026-07-12 (SUMMARIZED 2026-07-12)

Summarized by an earlier version of the skill.

---
## 2026-08-20

Recent section past any sensible cutoff.
"""

ORIGINAL_0710 = ("## 2026-07-10\n\nA long paragraph of narrative that should be "
                 "compacted away eventually.\nAnother line of narrative padding to "
                 "give the section some real weight.\n\n### DECISIONS\n"
                 "- 2026-07-10 - a decision\n")

GOOD = ("## 2026-07-10\n- [x] REFINED 2026-10-22 (COMPACTED 2026-10-22)\n\n"
        "- **Big picture.** The narrative, in one takeaway.\n\n"
        "### DECISIONS\n- 2026-07-10 - a decision\n\n"
        "### QUESTIONS\n- None.\n\n"
        "### ACTIONS\n- [ ] follow up (owner: A; opened 2026-07-10)\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.note = self.dir / 'notes-meetings.md'
        self.note.write_text(NOTE, encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        return compact.main([str(a) for a in argv])

    def run_out(self, *argv):
        """Exit code and stdout of one in-process run."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = self.run_cli(*argv)
        return rc, buf.getvalue()

    def section(self, date):
        from vault_patterns import date_sections
        return next(s for s in date_sections(self.note) if s['date'] == date)

    def backup(self, heading='2026-07-10', project='DEMO'):
        """Back the section up; returns (exit code, backup path or None)."""
        rc, out = self.run_out('backup', self.note, heading, '--root', self.dir,
                               '--project', project, '--date', '2026-10-22')
        return rc, (Path(out.strip()) if rc == 0 else None)


class TestStatus(Base):
    def test_section_status_reads_stamps_and_subsections(self):
        from vault_patterns import date_sections
        st = [compact.section_status(s) for s in date_sections(self.note)]
        self.assertEqual([s['compacted'] for s in st], [False, True, True, False])
        self.assertEqual(st[0]['subsections'], ['DECISIONS'])
        self.assertEqual(st[0]['key'], 'notes-meetings.md#2026-07-10')
        self.assertEqual(st[0]['stamp'], '')

    def test_candidates_respect_the_cutoff_and_skip_done_sections(self):
        rc, out = self.run_out('candidates', self.note, '--before', '2026-08-01')
        self.assertEqual(rc, 0)
        self.assertEqual([r['key'] for r in json.loads(out)], ['notes-meetings.md#2026-07-10'])

    def test_inspect_reports_the_section(self):
        rc, out = self.run_out('inspect', self.note, '2026-07-10')
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)['hash'],
                         compact.section_status(self.section('2026-07-10'))['hash'])

    def test_missing_section_exits_2(self):
        self.assertEqual(self.run_out('inspect', self.note, '2026-01-01')[0], 2)

    def test_a_duplicate_heading_is_addressed_by_its_key_ordinal(self):
        self.note.write_text(NOTE + "\n---\n## 2026-07-10\n\nThe second meeting that day.\n",
                             encoding='utf-8')
        rc, out = self.run_out('inspect', self.note, '2026-07-10~2')
        self.assertEqual(rc, 0)
        st = json.loads(out)
        self.assertEqual(st['key'], 'notes-meetings.md#2026-07-10~2')
        rc, out = self.run_out('inspect', self.note, '2026-07-10')
        self.assertEqual(json.loads(out)['key'], 'notes-meetings.md#2026-07-10')
        self.assertEqual(self.run_out('inspect', self.note, '2026-07-10~1')[0], 0)
        self.assertEqual(self.run_out('inspect', self.note, '2026-07-10~3')[0], 2)
        rc, path = self.backup('2026-07-10~2')
        self.assertEqual(rc, 0)
        self.assertIn('The second meeting that day.', path.read_text(encoding='utf-8'))
        self.assertNotIn('narrative', path.read_text(encoding='utf-8'))

    def test_there_is_no_ledger_or_receipt_command(self):
        for cmd in ('record',):
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
                self.run_cli(cmd, 'notes-meetings.md#2026-07-10')
            self.assertEqual(cm.exception.code, 2)


class TestBackup(Base):
    def test_backup_holds_the_section_verbatim(self):
        sec = self.section('2026-07-10')
        rc, path = self.backup()
        self.assertEqual(rc, 0)
        self.assertEqual(path.read_text(encoding='utf-8'), sec['body'])
        want = (self.dir / '__archive' / '_BACKUPS' / 'compact-notes' / 'DEMO'
                / 'notes-meetings.md'
                / f"2026-10-22-2026-07-10@{compact.section_status(sec)['hash']}.md")
        self.assertEqual(path, want.resolve())

    def test_backup_is_idempotent(self):
        rc1, first = self.backup()
        rc2, second = self.backup()
        self.assertEqual((rc1, rc2), (0, 0))
        self.assertEqual(first, second)
        self.assertEqual(len(list(first.parent.iterdir())), 1)

    def test_backup_refuses_to_overwrite_a_different_file(self):
        _, path = self.backup()
        path.write_text('something else', encoding='utf-8')
        rc, _ = self.backup()
        self.assertEqual(rc, 6)
        self.assertEqual(path.read_text(encoding='utf-8'), 'something else')

    def test_backup_path_stays_under_the_root(self):
        rc, _ = self.backup(project='../escape')
        self.assertEqual(rc, 6)
        self.assertFalse((self.dir / '__archive').exists())
        self.note.write_text(NOTE + '\n## 2026-07-13-A/../../B\n\nSlash suffix.\n',
                             encoding='utf-8')
        rc, path = self.backup(heading='2026-07-13-A/../../B')
        self.assertEqual(rc, 0)
        base = (self.dir / '__archive' / '_BACKUPS' / 'compact-notes').resolve()
        self.assertTrue(path.is_relative_to(base))
        self.assertNotIn('/', path.name)

    def test_missing_section_exits_2(self):
        rc, _ = self.backup(heading='2026-01-01')
        self.assertEqual(rc, 2)

    def test_date_must_be_an_iso_date(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            self.run_cli('backup', self.note, '2026-07-10', '--root', self.dir,
                         '--project', 'DEMO', '--date', '../../OTHER/x')
        self.assertEqual(cm.exception.code, 2)

    @needs_symlinks
    def test_symlinked_archive_leaving_the_root_is_refused(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.dir / '__archive').symlink_to(outside)
            rc, _ = self.backup()
            self.assertEqual(rc, 6)
            self.assertEqual(list(Path(outside).iterdir()), [])


class Rewritten(Base):
    """A section backed up, then overwritten in place the way the skill does it."""

    def setUp(self):
        super().setUp()
        self.pre_hash = compact.section_status(self.section('2026-07-10'))['hash']
        rc, self.backup_path = self.backup()
        self.assertEqual(rc, 0)

    def rewrite(self, body):
        self.note.write_text(NOTE.replace(ORIGINAL_0710, body), encoding='utf-8')

    def verify(self, *extra, backup=None, pre_hash=None):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return self.run_cli('verify', self.note, '2026-07-10',
                                '--backup', backup or self.backup_path,
                                '--pre-hash', pre_hash or self.pre_hash, *extra)


class TestVerify(Rewritten):
    def test_the_fixed_format_passes(self):
        self.rewrite(GOOD)
        self.assertEqual(self.verify('--pre-subs', 'DECISIONS'), 0)

    def test_each_required_subsection_is_needed(self):
        for sub in ('DECISIONS', 'QUESTIONS', 'ACTIONS'):
            start = GOOD.index(f'### {sub}')
            end = GOOD.find('\n\n###', start)
            self.rewrite(GOOD[:start] + (GOOD[end + 2:] if end != -1 else ''))
            self.assertEqual(self.verify(), 4, sub)

    def test_a_kept_subsection_must_survive(self):
        self.rewrite(GOOD + '\n')
        self.assertEqual(self.verify('--pre-subs', 'DECISIONS,RISKS'), 4)

    def test_the_stamp_and_its_marker_are_needed(self):
        self.rewrite(GOOD.replace('- [x] REFINED 2026-10-22 (COMPACTED 2026-10-22)\n', ''))
        self.assertEqual(self.verify(), 4)
        self.rewrite(GOOD.replace(' (COMPACTED 2026-10-22)', ''))
        self.assertEqual(self.verify(), 4)

    def test_invisible_characters_fail(self):
        for cp in (0x200B, 0x00A0, 0x2028, 0x2029, 0x0085):
            self.rewrite(GOOD.replace('one takeaway', f'one{chr(cp)}takeaway'))
            self.assertEqual(self.verify(), 4)

    def test_missing_backup_fails(self):
        self.rewrite(GOOD)
        self.assertEqual(self.verify(backup=self.dir / 'nowhere.md'), 4)

    def test_backup_not_matching_the_pre_edit_hash_fails(self):
        self.rewrite(GOOD)
        self.assertEqual(self.verify(pre_hash='000000000000'), 4)

    def test_tampered_backup_fails(self):
        self.rewrite(GOOD)
        self.backup_path.write_text('not the original', encoding='utf-8')
        self.assertEqual(self.verify(), 4)

    def test_backup_taken_after_the_edit_fails(self):
        self.rewrite(GOOD)
        late_hash = compact.section_status(self.section('2026-07-10'))['hash']
        _, late_backup = self.backup()
        self.assertEqual(self.verify(backup=late_backup, pre_hash=late_hash), 4)

    def test_verify_requires_the_backup_arguments(self):
        self.rewrite(GOOD)
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            self.run_cli('verify', self.note, '2026-07-10')
        self.assertEqual(cm.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
