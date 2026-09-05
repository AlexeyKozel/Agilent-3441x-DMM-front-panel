# Publication Checklist — 1.2.1

- [x] The package describes only the original front panel and its stock PPC/8051/ISP flow.
- [x] The external firmware identity is 4162 bytes and SHA-256 `55779328f8d9de6675ac3a145f846cfc3f86aaa346136698ef4df31edc15c4dd`; no manufacturer binary is required for ordinary model tests.
- [x] All three emulator READMEs state `NOT TESTED ON REAL HARDWARE` and make no hardware-validation claim.
- [x] The changelog distinguishes corrections, current-tree firmware removal, and preserved historical tags.
- [x] The final tree contains no firmware binary, Cyrillic text, PDFs, Ghidra artifacts, generated caches, logs, dumps, archives, or secrets.
- [x] `python -B -m unittest discover -s tests -v` completes successfully; unavailable external-evidence tests are explicitly reported as skipped.
- [x] The C tests complete with `FP_REQUIRE_C_COMPILER=1`; a missing or failing compiler fails this gate.
- [x] The full evidence audit completes with an explicit `FP_ORIGINAL_FIRMWARE` path and `FP_REQUIRE_ORIGINAL_FIRMWARE=1`; a missing or invalid image fails this gate.
- [x] Provenance hashes identify the final LF publication bytes and preserve historical evidence identities separately.
- [x] `python -B tools/verify_release.py` passes on the final clean checkout, and `SHA256SUMS.txt` matches it.
- [x] The final diff has been reviewed; publication uses a new version and preserves earlier tags.

Publication changes were explicitly authorized by the project owner. These checks record validation of the concrete release tree, not hardware approval.
