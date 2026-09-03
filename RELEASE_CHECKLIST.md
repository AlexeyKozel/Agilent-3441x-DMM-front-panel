# Publication Checklist

- [x] The owner has reviewed `README.md`, the MIT license, and `NOTICE.md`.
- [x] The package describes only the original front panel and its stock PPC/8051/ISP flow.
- [x] The included firmware identity is exactly 4162 bytes and SHA-256 `55779328f8d9de6675ac3a145f846cfc3f86aaa346136698ef4df31edc15c4dd`.
- [x] All three emulator READMEs state `NOT TESTED ON REAL HARDWARE` and make no hardware-validation claim.
- [x] `python -m unittest discover -s tests -v` completes successfully.
- [x] `python tools/verify_release.py` completes successfully.
- [x] No Cyrillic text, unrelated firmware, PDFs, Ghidra artifacts, logs, dumps, archives, or secrets are present.
- [x] `SHA256SUMS.txt` matches the final package contents.
- [x] The diff against the target GitHub repository has been reviewed.
- [x] The owner has given separate, explicit publication approval.
- [x] Only then are commit, push, and release operations performed.