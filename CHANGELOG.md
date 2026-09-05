# Changelog

## 1.2.1 — 2026-09-05

- Correct normal application reset in the Python and C99 panel models: apply the original initializer's 150 `FF` framebuffer bytes and enabled software IRQ gate, with P1.4 high as the startup assumption.
- Apply every `0x21` payload byte to XRAM immediately, preserve completed stores across CMMD resynchronization, and remove the MCU model's unsupported framebuffer-span rejection. Keep the stock PPC host span check.
- Preserve command `0x36` as a raw diagnostic counter and test its previous value against 30 independently of disabled loop history. Clarify the first-sample startup-held key behavior and correct trace labels.
- Add regression coverage and an independent bounded firmware oracle. An original image must be supplied explicitly through `--firmware` or `FP_ORIGINAL_FIRMWARE`; it is validated by length and SHA-256. Missing optional inputs are reported as skips; `FP_REQUIRE_ORIGINAL_FIRMWARE=1` makes the image mandatory for a full evidence audit.
- Correct stock update documentation: configuration values are read and reported with response validation, without an inferred comparison to expected settings. Clarify each sector's security/erase order and the `2E 0D 0A` success suffix.
- Use canonical LF text, recompute release checksums from publication bytes, and distinguish historical local export hashes from current public artifact hashes. Verification examples use `python -B` to avoid generated caches.
- Make detected C compiler failures fail tests; `FP_REQUIRE_C_COMPILER=1` also makes an absent compiler fail full C validation.
- Remove the original firmware binary from the current release tree and describe it as external evidence. Historical tags and Git history remain unchanged and may still contain the binary; this release does not purge history or rewrite earlier tags.

All three emulators remain offline research models and have not been tested on real hardware. The bounded oracle does not emulate the complete MCU, internal ROM, or physical peripherals.
