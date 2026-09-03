"""Scaffolder: seeds 14 files, never overwrites, and is byte-identical across runs."""
from __future__ import annotations

import filecmp
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCAFFOLD = SKILL / "scripts" / "vault_scaffold.py"
TEMPLATE = SKILL / "templates" / "PROJECTS"
SEED_COUNT = 14


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCAFFOLD), *args], capture_output=True, text=True)


def test_seed_writes_every_template_file(tmp_path: Path) -> None:
    result = run("--target", str(tmp_path), "--name", "TEST")
    assert result.returncode == 0, result.stderr
    dest = tmp_path / "PROJECTS" / "TEST"
    names = sorted(p.name for p in dest.iterdir())
    assert names == sorted(p.name for p in TEMPLATE.iterdir())
    assert len(names) == SEED_COUNT
    match, mismatch, errors = filecmp.cmpfiles(TEMPLATE, dest, names, shallow=False)
    assert not mismatch and not errors


def test_rerun_skips_everything_and_writes_nothing(tmp_path: Path) -> None:
    run("--target", str(tmp_path), "--name", "TEST")
    dest = tmp_path / "PROJECTS" / "TEST"
    (dest / "00-brd.md").write_text("edited by hand\n")
    before = {p.name: p.stat().st_mtime_ns for p in dest.iterdir()}
    result = run("--target", str(tmp_path), "--name", "TEST")
    assert result.returncode == 0
    assert result.stdout.count("skipped") == SEED_COUNT + 1  # summary line plus one per file
    assert (dest / "00-brd.md").read_text() == "edited by hand\n"
    assert {p.name: p.stat().st_mtime_ns for p in dest.iterdir()} == before


def test_partial_vault_gets_only_the_gaps(tmp_path: Path) -> None:
    dest = tmp_path / "PROJECTS" / "TEST"
    dest.mkdir(parents=True)
    (dest / "index.md").write_text("mine\n")
    result = run("--target", str(tmp_path), "--name", "TEST")
    assert result.returncode == 0
    assert (dest / "index.md").read_text() == "mine\n"
    assert len(list(dest.iterdir())) == SEED_COUNT


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    result = run("--target", str(tmp_path), "--name", "TEST", "--dry-run")
    assert result.returncode == 0
    assert not (tmp_path / "PROJECTS").exists()
    assert result.stdout.count("would write") == SEED_COUNT + 1


def test_two_seeds_are_byte_identical(tmp_path: Path) -> None:
    run("--target", str(tmp_path / "a"), "--name", "X")
    run("--target", str(tmp_path / "b"), "--name", "X")
    cmp = filecmp.dircmp(tmp_path / "a" / "PROJECTS" / "X", tmp_path / "b" / "PROJECTS" / "X")
    assert not cmp.diff_files and not cmp.left_only and not cmp.right_only


def test_name_must_be_a_single_visible_folder(tmp_path: Path) -> None:
    for bad in ("a/b", ".hidden", "..", "tab\there"):
        assert run("--target", str(tmp_path), "--name", bad).returncode == 2, bad


def test_symlinked_file_is_refused_not_followed(tmp_path: Path) -> None:
    dest = tmp_path / "PROJECTS" / "T"
    dest.mkdir(parents=True)
    outside = tmp_path / "OUTSIDE.md"
    (dest / "log.md").symlink_to(outside)
    result = run("--target", str(tmp_path), "--name", "T")
    assert result.returncode == 1
    assert not outside.exists()
    assert "log.md" in result.stdout and "symlink" in result.stdout
    assert len([p for p in dest.iterdir() if not p.is_symlink()]) == SEED_COUNT - 1


def test_symlinked_projects_dir_is_refused(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "PROJECTS").symlink_to(elsewhere)
    result = run("--target", str(tmp_path / "v"), "--name", "T")
    assert result.returncode == 1
    assert not any(elsewhere.iterdir())
