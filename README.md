# Agilent 34410A/34411A Original Front-Panel Protocol

This repository documents a static reconstruction of the interface between the main processor in the Agilent 34410A/34411A and the original 8051-based front-panel controller, with offline models and bounded checks for explicitly supplied evidence.

## Status

This is the public `1.2.1` release, prepared on 2026-09-05. See [CHANGELOG.md](CHANGELOG.md) for corrections to the previous release; historical tags are preserved.

The following areas are statically closed:

- 625000 bit/s, 9-bit runtime UART framing and command resynchronization;
- parser states, success mask, and every implemented command;
- 150-byte framebuffer, 600 two-bit cells, character positions, and 19 annunciators;
- 5x4 key matrix, debounce, four-entry FIFO, SRQ behavior, and event encoding;
- tone tables and sound sequences;
- J1102 pinout and the schematic-confirmed nominal 3.3 V logic domain;
- original 8051 reset/init, cooperative main loop, UART ISR/parser, VFD refresh, keypad, FIFO/SRQ, sound engine, and ROM-service call sites;
- the stock update path: the original 8051 image embedded in both PPC APPs, 7200 bit/s DOWN mode, ASCII HEX ISP records, responses, and erase/program order.

The original front-panel application image is external evidence: 4162 bytes, SHA-256 `55779328f8d9de6675ac3a145f846cfc3f86aaa346136698ef4df31edc15c4dd`. It was verified as byte-identical to the slice embedded in both studied PPC APP images. Version 1.2.1 removes the binary from the current release tree. Historical tags and Git history remain unchanged and may still contain it; this removal does not purge history.

Bench-measured voltage levels, edge quality, reset/break timing, and absolute sound frequencies remain open. The MCU's internal ROM implementation behind entry `0xFF03` is not part of the 4162-byte application image; its wire contract and the stock PPC host flow are nevertheless statically closed.

## Repository contents

- [docs/PROTOCOL.md](docs/PROTOCOL.md) - complete runtime protocol;
- [docs/ORIGINAL_MCU_INTERNALS.md](docs/ORIGINAL_MCU_INTERNALS.md) - operation of the original 8051 MCU;
- [docs/ORIGINAL_FIRMWARE_UPDATE.md](docs/ORIGINAL_FIRMWARE_UPDATE.md) - stock firmware update and ISP wire protocol;
- [docs/PHYSICAL_INTERFACE.md](docs/PHYSICAL_INTERFACE.md) - J1102 and electrical evidence boundaries;
- [docs/PROVENANCE.md](docs/PROVENANCE.md) - source identities and method;
- [docs/FIRMWARE_ORACLE.md](docs/FIRMWARE_ORACLE.md) - bounded independent checks that execute selected paths from an explicitly supplied external firmware image;
- [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) - unresolved items;
- [docs/ORIGINAL_PROCEDURE_PSEUDOCODE.md](docs/ORIGINAL_PROCEDURE_PSEUDOCODE.md) - independently rewritten pseudocode of key original 8051 and PPC procedures;
- `data/` and `derived/` - exact machine-readable facts and closure traces;
- [`emulators/front_panel_python/`](emulators/front_panel_python/) - Python emulator and reference model of the original front-panel MCU behavior;
- [`emulators/front_panel_c99/`](emulators/front_panel_c99/) - target-neutral C99 emulator of the original front-panel MCU behavior;
- [`emulators/ppc_host/`](emulators/ppc_host/) - Python emulator of the stock PPC-side transaction wrapper;
- `tests/` - offline protocol, publication-data, Python FP, and PPC emulator tests;
- `tools/verify_release.py` - fail-closed structure, language, recorded evidence identities, binary-absence, and checksum validation.

## Emulator validation boundary

**NOT TESTED ON REAL HARDWARE: Python FP, C99 FP, and PPC host emulators.**

They have been validated only through offline unit tests, deterministic traces, bounded firmware execution, C-to-Python differential checks, and bounded fuzz inputs. Normal application reset assumes P1.4 high and includes the compiler initializer: framebuffer `FF` repeated 150 times and software key IRQ gate enabled. Display payload bytes take effect as they arrive, including incomplete streams and spans outside the stock PPC's display bounds. They have not been connected to a real 34410A, 34411A, original front panel, UART, reset/SRQ line, VFD, keypad, or J1102 connector. Passing these tests does not establish target ABI correctness, real-time behavior, electrical compatibility, signal integrity, or safe operation on an instrument.

## Verification

Python 3.11 or newer is required; no third-party packages are needed.

```text
python -B -m unittest discover -s tests -v
python -B -m unittest -v emulators/front_panel_c99/test_differential.py emulators/front_panel_c99/test_audit.py
python -B tools/verify_release.py
```

The C checks require a C99 compiler. Optional local checks may skip when no compiler is available; a detected compiler's build failure is a test failure. For full C validation, set `FP_REQUIRE_C_COMPILER=1` before running the commands so that a missing compiler also fails. In PowerShell use `$env:FP_REQUIRE_C_COMPILER = '1'`; in a POSIX shell use `export FP_REQUIRE_C_COMPILER=1`. The `-B` option keeps these commands from creating bytecode caches that the release verifier rejects.

Firmware-backed tests explicitly skip when no external image is supplied. Keep the image outside the publication tree. Set `FP_ORIGINAL_FIRMWARE` to its path and `FP_REQUIRE_ORIGINAL_FIRMWARE=1` for a full evidence audit; the required length and SHA-256 are checked, and an invalid supplied image fails. The oracle can also be run directly:

```text
python -B tools/firmware_oracle.py --firmware /path/to/34410A_front_panel_firmware.bin
```

Public text uses LF line endings. Verify the committed files in a clean checkout; `SHA256SUMS.txt` identifies the final published bytes. Public-only tests validate the reconstructed models and package; executing original MCU paths additionally requires the external image. Repeating the PPC ISP reconstruction requires the separately obtained APP images identified in [PROVENANCE.md](docs/PROVENANCE.md). Tools do not download firmware or search private project directories.

## Safety notice

This is not a service procedure for live equipment or an invitation to reflash an instrument without a recovery path. `FILP`, `FILN`, and `+12V_UNREG` are not 3.3 V logic. Work on J1102 requires independent confirmation of common, power sequencing, reset/SRQ/power-fail polarity, and safe levels on the actual unit.

## Licensing

The independently created repository contents are licensed under the MIT License; see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md). Manufacturer firmware images are external inputs and are not included in this release tree.
