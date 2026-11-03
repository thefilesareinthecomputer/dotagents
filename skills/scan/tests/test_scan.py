"""Tests for scripts/scan.py. The external tools are replaced by stub programs on PATH,
driven by a JSON file, so the parsing, the update rule and the verdicts are tested without
a live system or the network. The sweep uses the real /usr/bin/find and xattr. One live
test runs the real clamscan (with --no-update) on an EICAR file built at run time, when
clamscan is installed.

Run: python3 -m unittest discover -s tests -v
"""
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "scan.py"

STUB = r'''#!PYTHON
import json, os, sys
name = os.path.basename(sys.argv[0])
cfg = json.load(open(os.environ["STUB_CONFIG"]))
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps([name] + sys.argv[1:]) + "\n")
args = sys.argv[1:]
target = args[-1] if args else ""
base = os.path.basename(target)
marker = os.environ["STUB_LOG"] + ".updated"
if name == "freshclam":
    print(cfg.get("fresh_out", "daily.cld updated"))
    rc = cfg.get("fresh_rc", 0)
    if rc in (0, 1):
        open(marker, "w").close()
    sys.exit(rc)
if name == "clamscan":
    if args == ["--version"]:
        updated = os.path.exists(marker) and "clam_version_after" in cfg
        print(cfg["clam_version_after"] if updated else cfg["clam_version"]); sys.exit(0)
    found = cfg.get("clam_found", [])
    for f, sig in found:
        print(f"{f}: {sig} FOUND")
    print("----------- SCAN SUMMARY -----------")
    print(f"Scanned files: {cfg.get('clam_scanned', 1)}")
    print(f"Infected files: {len(found)}")
    sys.exit(cfg.get("clam_rc", 1 if found else 0))
if name == "clamconf":
    print(f"Checking configuration files in {cfg['conf_dir']}"); sys.exit(0)
if name == "xprotect":
    print(cfg.get("xprotect", "Version: 5368 Installed: 2099-01-01 00:00:00 +0000")); sys.exit(0)
if name == "spctl":
    if args == ["--status"]:
        print(cfg.get("gk_status", "assessments enabled")); sys.exit(0)
    verdict, source = cfg.get("gk", {}).get(base, ["accepted", "Notarized Developer ID"])
    sys.stderr.write(f"{target}: {verdict}\n" + (f"source={source}\n" if source else ""))
    sys.exit(0 if verdict == "accepted" else 3)
if name == "codesign":
    state = cfg.get("cs", {}).get(base, "valid")
    if args[0] == "-dv":
        signer = cfg.get("signer", {}).get(base, "devid")
        if signer == "adhoc":
            sys.stderr.write("Executable=x\nSignature=adhoc\nTeamIdentifier=not set\n")
        else:
            sys.stderr.write("Executable=x\nAuthority=Developer ID Application: Example Corp (ABCDE12345)\n"
                             "Authority=Developer ID Certification Authority\nAuthority=Apple Root CA\n"
                             "TeamIdentifier=ABCDE12345\n")
        sys.exit(0)
    if state == "valid": sys.exit(0)
    sys.stderr.write(f"{target}: " + ("code object is not signed at all" if state == "unsigned" else "a sealed resource is missing or invalid") + "\n")
    sys.exit(1)
if name == "pkgutil":
    status = cfg.get("pkg_status", "signed by a developer certificate issued by Apple for distribution")
    print("Package \"x\":")
    print("   Status: " + status)
    if "no signature" not in status:
        print("   Certificate Chain:")
        print("    1. Developer ID Installer: Example Corp (ABCDE12345)")
    sys.exit(0 if "no signature" not in status else 1)
if name == "xattr":
    q = cfg.get("quarantine", {}).get(base)
    if q: print(q); sys.exit(0)
    sys.exit(1)
if name == "mdls":
    print(cfg.get("where", {}).get(base, "(null)")); sys.exit(0)
'''.replace("PYTHON", sys.executable)

TOOLS = ("clamscan", "freshclam", "clamconf", "xprotect", "spctl", "codesign", "pkgutil", "xattr", "mdls")
FRESH = "ClamAV 1.5.2/28167/Wed Oct 28 01:24:17 2099"   # a build date in the future is never stale
OLD = "ClamAV 1.5.2/26000/Mon Jan  1 00:00:00 2024"
MACHO = b"\xcf\xfa\xed\xfe" + b"\x00" * 60
JAVA_CLASS = b"\xca\xfe\xba\xbe\x00\x00\x00\x34" + b"\x00" * 56


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.target = self.tmp / "target"
        self.target.mkdir()
        self.log = self.tmp / "calls.log"
        self.confdir = self.tmp / "etc-clamav"
        self.confdir.mkdir()
        (self.confdir / "freshclam.conf").write_text("# Comment\n#Example\nDatabaseMirror database.clamav.net\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def scan(self, path, cfg, tools=TOOLS, extra=()):
        for t in tools:
            p = self.bin / t
            p.write_text(STUB)
            p.chmod(0o755)
        cfg = dict(cfg, conf_dir=str(self.confdir))
        cfg_file = self.tmp / "cfg.json"
        cfg_file.write_text(json.dumps(cfg))
        env = dict(os.environ, PATH=str(self.bin), STUB_CONFIG=str(cfg_file), STUB_LOG=str(self.log))
        proc = subprocess.run([sys.executable, str(SCRIPT), str(path), "--json", *extra],
                              capture_output=True, text=True, env=env)
        report = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else None
        return proc.returncode, report, proc

    def calls(self, tool):
        if not self.log.exists():
            return []
        return [c for c in map(json.loads, self.log.read_text().splitlines()) if c[0] == tool]

    def make_app(self, name, exe_bytes=MACHO):
        app = self.target / name
        (app / "Contents" / "MacOS").mkdir(parents=True)
        with open(app / "Contents" / "Info.plist", "wb") as f:
            plistlib.dump({"CFBundleExecutable": "main"}, f)
        (app / "Contents" / "MacOS" / "main").write_bytes(exe_bytes)
        return app

    # ClamAV lane and the signature update

    def test_clean_file(self):
        f = self.target / "notes.txt"
        f.write_text("hello")
        rc, rep, _ = self.scan(f, {"clam_version": FRESH})
        self.assertEqual((rc, rep["verdict"]), (0, "clean"))
        self.assertEqual(rep["clamav"]["warnings"], [])

    def test_infected_file_is_a_finding_and_never_removed(self):
        f = self.target / "bad.bin"
        f.write_text("x")
        rc, rep, _ = self.scan(f, {"clam_version": FRESH, "clam_found": [[str(f), "Win.Test.EICAR_HDB-1"]]})
        self.assertEqual(rc, 1)
        self.assertEqual(rep["clamav"]["found"], [{"file": str(f), "signature": "Win.Test.EICAR_HDB-1"}])
        for call in self.calls("clamscan"):
            self.assertFalse(any(a.startswith(("--remove", "--move", "--copy")) for a in call), call)
        self.assertTrue(f.exists())

    def test_an_infection_exit_with_no_parsed_line_is_still_a_finding(self):
        rc, rep, _ = self.scan(self.target, {"clam_version": FRESH, "clam_rc": 1})
        self.assertEqual((rc, rep["verdict"], len(rep["clamav"]["found"])), (1, "findings", 1))

    def test_a_bundle_executable_name_cannot_leave_the_bundle(self):
        app = self.make_app("Escape.app")
        with open(app / "Contents" / "Info.plist", "wb") as f:
            plistlib.dump({"CFBundleExecutable": "../../../outside"}, f)
        rc, rep, _ = self.scan(app, {"clam_version": FRESH})
        self.assertIsNone(rep["apple"]["items"][0]["sha256"])
        with open(app / "Contents" / "Info.plist", "wb") as f:
            plistlib.dump({"CFBundleExecutable": 7}, f)
        rc, rep, _ = self.scan(app, {"clam_version": FRESH})
        self.assertIsNone(rep["apple"]["items"][0]["sha256"])
        outside = self.tmp / "outside"
        outside.write_bytes(MACHO)
        (app / "Contents" / "MacOS" / "main").unlink()
        (app / "Contents" / "MacOS" / "main").symlink_to(outside)
        with open(app / "Contents" / "Info.plist", "wb") as f:
            plistlib.dump({"CFBundleExecutable": "main"}, f)
        rc, rep, _ = self.scan(app, {"clam_version": FRESH})
        self.assertIsNone(rep["apple"]["items"][0]["sha256"])

    def test_control_characters_in_a_file_name_are_escaped(self):
        self.make_app("Bad\x1b[31mName.app")
        env = dict(os.environ)
        rc, _, proc = self.scan(self.target, {"clam_version": FRESH})
        cfg_file = self.tmp / "cfg.json"
        proc = subprocess.run([sys.executable, str(SCRIPT), str(self.target)], capture_output=True, text=True,
                              env=dict(env, PATH=str(self.bin), STUB_CONFIG=str(cfg_file), STUB_LOG=str(self.log)))
        self.assertNotIn("\x1b", proc.stdout)
        self.assertIn("\\x1b", proc.stdout)

    def test_fresh_signatures_skip_the_update(self):
        rc, rep, _ = self.scan(self.target, {"clam_version": FRESH})
        self.assertEqual(self.calls("freshclam"), [])
        self.assertFalse(rep["clamav"]["update"]["ran"])

    def test_stale_signatures_update_before_the_scan(self):
        rc, rep, _ = self.scan(self.target, {"clam_version": OLD, "clam_version_after": FRESH})
        self.assertEqual(len(self.calls("freshclam")), 1)
        names = [c[0] for c in map(json.loads, self.log.read_text().splitlines())]
        self.assertLess(names.index("freshclam"), max(i for i, n in enumerate(names) if n == "clamscan"))
        self.assertEqual((rc, rep["clamav"]["warnings"]), (0, []))

    def test_failed_update_warns_and_still_scans(self):
        rc, rep, _ = self.scan(self.target, {"clam_version": OLD, "fresh_rc": 52,
                                             "fresh_out": "ERROR: Can't connect to port 443 of host"})
        self.assertEqual(rc, 0)
        warnings = " ".join(rep["clamav"]["warnings"])
        self.assertIn("signature update failed", warnings)
        self.assertIn("days old", warnings)
        self.assertIn("scanned_files", rep["clamav"])

    def test_no_update_flag_skips_freshclam(self):
        rc, rep, _ = self.scan(self.target, {"clam_version": OLD}, extra=["--no-update"])
        self.assertEqual(self.calls("freshclam"), [])
        self.assertTrue(any("freshclam" in w for w in rep["clamav"]["warnings"]))

    def test_outdated_engine_is_reported(self):
        rc, rep, _ = self.scan(self.target, {"clam_version": OLD, "clam_version_after": FRESH,
                                             "fresh_out": "WARNING: Your ClamAV installation is OUTDATED!"})
        self.assertTrue(any("brew upgrade clamav" in w for w in rep["clamav"]["warnings"]))

    def test_old_xprotect_rules_warn_with_the_root_command(self):
        rc, rep, _ = self.scan(self.target, {"clam_version": FRESH,
                                             "xprotect": "Version: 5000 Installed: 2024-01-01 00:00:00 +0000"})
        self.assertTrue(any("sudo xprotect update" in w for w in rep["apple"]["warnings"]))
        self.assertFalse(any(c[1:] != ["version"] for c in self.calls("xprotect")))

    # Apple lane

    def test_tampered_signature_is_a_finding(self):
        app = self.make_app("Edited.app")
        rc, rep, _ = self.scan(app, {"clam_version": FRESH, "cs": {"Edited.app": "invalid"}})
        self.assertEqual(rc, 1)
        self.assertEqual(rep["apple"]["items"][0]["level"], "finding")

    def test_adhoc_app_is_unverified_not_a_finding(self):
        app = self.make_app("Mine.app")
        rc, rep, _ = self.scan(app, {"clam_version": FRESH, "gk": {"Mine.app": ["rejected", ""]},
                                     "signer": {"Mine.app": "adhoc"}})
        item = rep["apple"]["items"][0]
        self.assertEqual((rc, rep["verdict"], item["level"]), (3, "unverified", "unverified"))
        self.assertEqual(item["signature"]["signer"]["kind"], "ad-hoc")
        self.assertIn("ad-hoc", item["reason"])

    def test_developer_id_signer_is_named(self):
        app = self.make_app("Good.app")
        rc, rep, _ = self.scan(app, {"clam_version": FRESH})
        signer = rep["apple"]["items"][0]["signature"]["signer"]
        self.assertEqual(rc, 0)
        self.assertEqual(signer, {"kind": "Developer ID", "team": "ABCDE12345",
                                  "authority": "Developer ID Application: Example Corp (ABCDE12345)"})

    def test_app_fingerprint_is_its_main_executable(self):
        app = self.make_app("Hashed.app")
        rc, rep, _ = self.scan(app, {"clam_version": FRESH})
        fp = rep["apple"]["items"][0]["sha256"]
        self.assertEqual(fp["file"], os.path.realpath(app / "Contents" / "MacOS" / "main"))
        self.assertEqual(fp["sha256"], hashlib.sha256(MACHO).hexdigest())

    def test_bare_program_is_checked_and_java_class_is_not(self):
        prog = self.target / "driver"
        prog.write_bytes(MACHO)
        prog.chmod(0o755)
        cls = self.target / "Thing.class"
        cls.write_bytes(JAVA_CLASS)
        cls.chmod(0o755)
        script = self.target / "run.sh"
        script.write_text("#!/bin/sh\n")
        script.chmod(0o755)
        rc, rep, _ = self.scan(self.target, {"clam_version": FRESH, "gk": {"driver": ["rejected", ""]},
                                             "signer": {"driver": "adhoc"}})
        items = rep["apple"]["items"]
        self.assertEqual([os.path.basename(i["item"]) for i in items], ["driver"])
        self.assertEqual((items[0]["kind"], items[0]["level"], rc), ("program", "unverified", 3))
        self.assertEqual(items[0]["sha256"]["sha256"], hashlib.sha256(MACHO).hexdigest())

    def test_walk_finds_apps_and_installers_without_entering_bundles(self):
        app = self.make_app("sub/Tool.app")
        (app / "Contents" / "Resources").mkdir()
        (app / "Contents" / "Resources" / "inner.pkg").write_text("x")
        (self.target / "setup.pkg").write_text("x")
        (self.target / "disk.dmg").write_text("x")
        rc, rep, _ = self.scan(self.target, {"clam_version": FRESH})
        names = sorted(os.path.basename(i["item"]) for i in rep["apple"]["items"])
        self.assertEqual(names, ["Tool.app", "disk.dmg", "setup.pkg"])
        self.assertEqual(rc, 0)

    def test_unsigned_dmg_is_a_note_not_a_finding(self):
        dmg = self.target / "installer.dmg"
        dmg.write_text("x")
        rc, rep, _ = self.scan(dmg, {"clam_version": FRESH,
                                     "gk": {"installer.dmg": ["rejected", "no usable signature"]},
                                     "cs": {"installer.dmg": "unsigned"}})
        self.assertEqual((rc, rep["apple"]["items"][0]["level"]), (0, "note"))
        self.assertIn("mount it", rep["apple"]["items"][0]["reason"])

    def test_unsigned_pkg_is_unverified(self):
        pkg = self.target / "setup.pkg"
        pkg.write_text("x")
        rc, rep, _ = self.scan(pkg, {"clam_version": FRESH, "pkg_status": "no signature",
                                     "gk": {"setup.pkg": ["rejected", "no usable signature"]}})
        self.assertEqual((rc, rep["apple"]["items"][0]["signature"]["state"]), (3, "unsigned"))

    def test_signed_pkg_names_its_signer(self):
        pkg = self.target / "ok.pkg"
        pkg.write_text("x")
        rc, rep, _ = self.scan(pkg, {"clam_version": FRESH})
        self.assertEqual(rep["apple"]["items"][0]["signature"]["signer"]["kind"], "Developer ID")

    def test_quarantine_and_origin_are_reported(self):
        self.make_app("Got.app")
        rc, rep, _ = self.scan(self.target, {"clam_version": FRESH,
                                             "quarantine": {"Got.app": "0083;6657a51a;Chrome;ABC"},
                                             "where": {"Got.app": '(\n    "https://example.com/got.zip",\n    "https://example.com/"\n)'}})
        item = rep["apple"]["items"][0]
        self.assertEqual(item["quarantine"]["agent"], "Chrome")
        self.assertRegex(item["quarantine"]["date"], r"^2024-05-\d\d ")
        self.assertEqual(item["origin"][0], "https://example.com/got.zip")

    def test_missing_clamscan_leads_through_setup_and_still_runs_apple_checks(self):
        self.make_app("A.app")
        (self.confdir / "freshclam.conf").unlink()
        rc, rep, _ = self.scan(self.target, {}, tools=[t for t in TOOLS if t != "clamscan"])
        self.assertEqual((rc, rep["clamav"]["status"]), (4, "setup-needed"))
        steps = rep["clamav"]["setup"]
        self.assertEqual(steps[0], "brew install clamav")
        self.assertIn("freshclam.conf.sample", steps[1])
        self.assertTrue(steps[-1].startswith("freshclam"))
        self.assertEqual(len(rep["apple"]["items"]), 1)

    def test_missing_config_gives_the_steps_and_changes_nothing(self):
        (self.confdir / "freshclam.conf").unlink()
        rc, rep, _ = self.scan(self.target, {"clam_version": FRESH})
        conf = str(self.confdir / "freshclam.conf")
        self.assertEqual(rep["clamav"]["setup"][:2],
                         [f'cp "{conf}.sample" "{conf}"', f"sed -i '' 's/^Example/#Example/' \"{conf}\""])
        self.assertEqual(self.calls("freshclam"), [])
        self.assertFalse(any(c[1:] != ["--version"] for c in self.calls("clamscan")))
        self.assertFalse((self.confdir / "freshclam.conf").exists())
        self.assertEqual(rc, 4)

    def test_an_active_example_line_is_a_setup_step(self):
        (self.confdir / "freshclam.conf").write_text("# Comment\nExample\n")
        rc, rep, _ = self.scan(self.target, {"clam_version": FRESH})
        self.assertEqual(len(rep["clamav"]["setup"]), 2)
        self.assertIn("#Example", rep["clamav"]["setup"][0])
        self.assertEqual(rc, 4)

    def test_no_signatures_yet_downloads_them_first(self):
        rc, rep, _ = self.scan(self.target, {"clam_version": "ClamAV 1.5.2", "clam_version_after": FRESH})
        self.assertEqual(len(self.calls("freshclam")), 1)
        self.assertEqual((rc, rep["clamav"]["status"]), (0, "ok"))

    def test_signatures_still_missing_after_the_update_is_an_error_not_a_scan(self):
        rc, rep, _ = self.scan(self.target, {"clam_version": "ClamAV 1.5.2", "fresh_rc": 52})
        self.assertEqual((rc, rep["clamav"]["status"]), (4, "error"))
        self.assertIn("no signatures", rep["clamav"]["note"])
        self.assertFalse(any(c[1:] != ["--version"] for c in self.calls("clamscan")))

    def test_bad_path(self):
        rc, _, proc = self.scan(self.target / "nope", {"clam_version": FRESH})
        self.assertEqual(rc, 2)
        self.assertIn("no such file", proc.stderr)

    # Sweep

    def downloaded(self, path):
        subprocess.run(["/usr/bin/xattr", "-w", "com.apple.quarantine", "0083;6657a51a;Chrome;", str(path)], check=True)

    def test_sweep_flags_local_files_and_instruction_files(self):
        (self.target / "dropped").mkdir()
        (self.target / "dropped" / "AGENTS.md").write_text("x")
        (self.target / "dropped" / "payload.command").write_text("x")
        got = self.target / "report.pdf"
        got.write_text("x")
        self.downloaded(got)
        (self.target / ".DS_Store").write_text("x")
        rc, rep, _ = self.scan(self.target, {}, extra=["--sweep"])
        made = rep["made_on_this_mac"]
        self.assertEqual(rc, 3)
        self.assertEqual(made["by_folder"], {"dropped": 3})   # the folder and its two files
        self.assertNotIn(str(os.path.realpath(got)), made["paths"])
        self.assertEqual([os.path.basename(p) for p in rep["instruction_files"]], ["AGENTS.md"])
        self.assertEqual(rep["runnable_by_folder"], {"dropped": 1})
        self.assertEqual(self.calls("clamscan"), [])

    def test_sweep_of_downloaded_files_is_clean(self):
        got = self.target / "setup.dmg"
        got.write_text("x")
        self.downloaded(got)
        rc, rep, _ = self.scan(self.target, {}, extra=["--sweep"])
        self.assertEqual((rc, rep["verdict"], rep["made_on_this_mac"]["count"]), (0, "clean", 0))

    def test_sweep_since_rejects_a_bad_date(self):
        rc, _, proc = self.scan(self.target, {}, extra=["--sweep", "--since", "last week"])
        self.assertEqual(rc, 2)

    @unittest.skipUnless(shutil.which("clamscan"), "clamscan not installed")
    def test_live_eicar(self):
        eicar = self.target / "eicar.com"
        # the EICAR test string, assembled at run time so this file is never itself flagged
        eicar.write_text("X5O!P%@AP[4\\PZX54(P^)7CC)7}" + "$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*")
        proc = subprocess.run([sys.executable, str(SCRIPT), str(eicar), "--json", "--no-update"],
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(len(json.loads(proc.stdout)["clamav"]["found"]), 1)
        self.assertTrue(eicar.exists())


if __name__ == "__main__":
    unittest.main()
