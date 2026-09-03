# Agilent 34410A/34411A Original Front-Panel Protocol

This repository is a reproducible static reconstruction of the interface between the main processor in the Agilent 34410A/34411A and the original 8051-based front-panel controller.

## Status

Release candidate `1.0.1`, prepared on 2026-09-03. This is the public `1.0.1` release. The project can be extended through normal subsequent commits and tagged releases.

The following areas are statically closed:

- 625000 bit/s, 9-bit runtime UART framing and command resynchronization;
- parser states, success mask, and every implemented command;
- 150-byte framebuffer, 600 two-bit cells, character positions, and 19 annunciators;
- 5x4 key matrix, debounce, four-entry FIFO, SRQ behavior, and event encoding;
- tone tables and sound sequences;
- J1102 pinout and the schematic-confirmed nominal 3.3 V logic domain;
- original 8051 reset/init, cooperative main loop, UART ISR/parser, VFD refresh, keypad, FIFO/SRQ, sound engine, and ROM-service call sites;
- the stock update path: the original 8051 image embedded in both PPC APPs, 7200 bit/s DOWN mode, ASCII HEX ISP records, responses, and erase/program order.

The exact original front-panel application image is included as [`firmware/34410A_front_panel_firmware.bin`](firmware/34410A_front_panel_firmware.bin): 4162 bytes, SHA-256 `55779328f8d9de6675ac3a145f846cfc3f86aaa346136698ef4df31edc15c4dd`. It is byte-identical to the slice embedded in both studied PPC APP images.

Bench-measured voltage levels, edge quality, reset/break timing, and absolute sound frequencies remain open. The MCU's internal ROM implementation behind entry `0xFF03` is not part of the 4162-byte application image; its wire contract and the stock PPC host flow are nevertheless statically closed.

## Repository contents

- [docs/PROTOCOL.md](docs/PROTOCOL.md) - complete runtime protocol;
- [docs/ORIGINAL_MCU_INTERNALS.md](docs/ORIGINAL_MCU_INTERNALS.md) - operation of the original 8051 MCU;
- [docs/ORIGINAL_FIRMWARE_UPDATE.md](docs/ORIGINAL_FIRMWARE_UPDATE.md) - stock firmware update and ISP wire protocol;
- [docs/PHYSICAL_INTERFACE.md](docs/PHYSICAL_INTERFACE.md) - J1102 and electrical evidence boundaries;
- [docs/PROVENANCE.md](docs/PROVENANCE.md) - source identities and method;
- [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) - unresolved items;
- `data/` and `derived/` - exact machine-readable facts and closure traces;
- `reference_model/` and `tests/` - deterministic offline behavioral model;
- `tools/verify_release.py` - fail-closed structure, language, binary identity, and checksum validation.

## Verification

Python 3.11 or newer is required; no third-party packages are needed.

```text
python -m unittest discover -s tests -v
python tools/verify_release.py
```

## Safety notice

This is not a service procedure for live equipment or an invitation to reflash an instrument without a recovery path. `FILP`, `FILN`, and `+12V_UNREG` are not 3.3 V logic. Work on J1102 requires independent confirmation of common, power sequencing, reset/SRQ/power-fail polarity, and safe levels on the actual unit.

## Licensing

The independently created repository contents are licensed under the MIT License; see [LICENSE](LICENSE). The included original firmware image is accompanied by the provenance and rights notice in [NOTICE.md](NOTICE.md).