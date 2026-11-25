"""The checkpoint `ingest --keep-previous` writes goes through a temp file
the ingest creates itself, so a link planted at a predictable temp name is
never written through."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import markdown_kg as kg  # noqa: E402

# Creating a symlink on Windows needs Developer Mode or admin rights.
needs_symlinks = unittest.skipIf(sys.platform == "win32",
                                 "symlinks need Developer Mode or admin rights on Windows")


class CheckpointTempTests(unittest.TestCase):
    @needs_symlinks
    def test_a_link_at_the_old_temp_name_is_left_alone(self):
        tmp = Path(tempfile.mkdtemp(prefix="mkg-ckpt-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        vault = tmp / "vault"
        vault.mkdir()
        (vault / "a.md").write_text("# A\n", encoding="utf-8")
        kg.ingest(vault)
        prev = kg.prev_db_path(vault)
        target = tmp / "planted"
        target.write_bytes(b"keep")
        os.symlink(target, prev.with_name(prev.name + ".tmp"))
        live = kg.db_path(vault).read_bytes()
        report = kg.ingest(vault, keep_previous=True)
        self.assertEqual(target.read_bytes(), b"keep")
        self.assertEqual(prev.read_bytes(), live)
        self.assertEqual(report["checkpoint"], str(prev))


class LinkedStoreTests(unittest.TestCase):
    @needs_symlinks
    def test_a_linked_engine_folder_is_refused(self):
        tmp = Path(tempfile.mkdtemp(prefix="mkg-link-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        vault, outside = tmp / "vault", tmp / "outside"
        vault.mkdir()
        outside.mkdir()
        (vault / "a.md").write_text("# A\n", encoding="utf-8")
        os.symlink(outside, vault / kg.KG_DIR)
        with self.assertRaises(SystemExit) as ctx:
            kg.ingest(vault)
        self.assertIn("link", str(ctx.exception.code))
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
