# Original Front-Panel C99 Emulator

This directory contains a target-neutral C99 emulator of the original 34410A/34411A front-panel MCU's digital runtime behavior. It models the reconstructed parser, replies, framebuffer, key FIFO/SRQ state, sound tables, diagnostic traffic, and the original `0x21 count=0` 256-write edge case.

The core contains no UART, GPIO, display driver, bootloader, dynamic memory, or MCU-specific HAL. Platform callbacks receive logical reply words, SRQ changes, and sound notifications. `test_host.c` is a deterministic PPC-side host harness, while `trace_runner.c` supports C-to-Python differential tests.

## Offline verification

```text
make test
python -m unittest -v emulators/front_panel_c99/test_differential.py emulators/front_panel_c99/test_audit.py
```

The publication review rebuilt the core with TinyCC 0.9.27 (x86_64 Windows), compiler SHA-256 `e9cb3e89e20a9efead83cc9e6b100314275634c2f705056da71f424ea9b0cdf0`. The C host harness passed, as did 13 source, boundary, deterministic, and bounded-fuzz differential tests against `emulators.front_panel_python.PanelModel`.

## Hardware status

**NOT TESTED ON REAL HARDWARE.**

The core has not been compiled for a production MCU or connected to a real instrument, original panel, UART, VFD, keypad, reset line, SRQ line, or J1102. Offline equivalence does not prove target ABI correctness, interrupt timing, baud-rate accuracy, electrical compatibility, signal integrity, or safe operation on hardware. ASan/UBSan and production-toolchain validation also remain open.