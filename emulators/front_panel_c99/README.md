# Original Front-Panel C99 Emulator

This directory contains a target-neutral C99 emulator of the original 34410A/34411A front-panel MCU's digital runtime behavior. It models the reconstructed parser, replies, framebuffer, key FIFO/SRQ state, sound tables, and raw diagnostic counter. Normal application reset assumes P1.4 high, fills the 150 framebuffer bytes with `FF`, and enables the software IRQ gate. Every `0x21` data byte writes the 512-byte XRAM window immediately; completed stores survive CMMD resynchronization. There is no MCU framebuffer-span rejection, and a count of zero requests 256 stores.

The core contains no UART, GPIO, display driver, bootloader, dynamic memory, or MCU-specific HAL. Platform callbacks receive logical reply words, SRQ changes, and sound notifications. `test_host.c` is a deterministic PPC-side host harness, while `trace_runner.c` supports C-to-Python differential tests.

## Offline verification

```text
make test
python -B -m unittest -v emulators/front_panel_c99/test_differential.py emulators/front_panel_c99/test_audit.py
```

The historical 1.2.0 review used TinyCC 0.9.27 (x86_64 Windows), compiler SHA-256 `e9cb3e89e20a9efead83cc9e6b100314275634c2f705056da71f424ea9b0cdf0`; its 13 tests did not detect all shared model errors. Version 1.2.1 corrects reset, incremental display stores, unchecked spans, and diagnostic phase and adds regression coverage.

Set `FP_REQUIRE_C_COMPILER=1` for full validation. Optional local checks may skip only when no compiler is available; failure of a detected compiler is a test failure. See the root [verification instructions](../../README.md#verification) and [bounded firmware oracle](../../docs/FIRMWARE_ORACLE.md) for the separate external-firmware input and strict audit settings.

## Hardware status

**NOT TESTED ON REAL HARDWARE.**

The core has not been compiled for a production MCU or connected to a real instrument, original panel, UART, VFD, keypad, reset line, SRQ line, or J1102. Offline equivalence does not prove target ABI correctness, interrupt timing, baud-rate accuracy, electrical compatibility, signal integrity, or safe operation on hardware. ASan/UBSan and production-toolchain validation also remain open.
