"""Release regressions: reject invalid artifacts before publishing checksums."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.copy = Path(self.temp.name) / "release"
        shutil.copytree(ROOT, self.copy, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".pytest_cache"))
        self.sums_before = (self.copy / "SHA256SUMS.txt").read_bytes()

    def reject_without_rewriting_sums(self, message):
        result = subprocess.run(
            [sys.executable, "-B", "tools/verify_release.py", "--write-sums"],
            cwd=self.copy, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)
        self.assertEqual((self.copy / "SHA256SUMS.txt").read_bytes(), self.sums_before)

    def test_crlf_checkout_cannot_generate_incompatible_checksums(self):
        readme = self.copy / "README.md"
        readme.write_bytes(readme.read_bytes().replace(b"\n", b"\r\n"))
        self.reject_without_rewriting_sums("canonical LF endings")

    def test_binary_cannot_be_accidentally_reintroduced(self):
        (self.copy / "accidental.bin").write_bytes(b"binary fixture")
        self.reject_without_rewriting_sums("forbidden artifact: accidental.bin")

    def test_redistribution_metadata_must_agree(self):
        path = self.copy / "data/original_firmware_update.json"
        update = json.loads(path.read_text(encoding="utf-8"))
        update["firmware_image"]["redistributed"] = True
        path.write_text(json.dumps(update), encoding="utf-8", newline="\n")
        self.reject_without_rewriting_sums("firmware is not redistributed")

    def test_unverified_bench_scope_cannot_be_marked_closed(self):
        path = self.copy / "release_manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["scope"]["bench_update_execution"] = "CLOSED"
        path.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
        self.reject_without_rewriting_sums("must remain OPEN")


if __name__ == "__main__":
    unittest.main()
