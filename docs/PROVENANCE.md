# Provenance and Reproducibility

## Source identities

| Source | SHA-256 / identity |
|---|---|
| 34410A PPC APP | `9d05d676bf87d5109f75150935d6a95d8422ce4ceec2e768f5538caba9d02c6b` |
| 34411A PPC APP | `435633c24c33b546bf7e708392a751719fc41ed58d9ab8cf9643d559748f8654` |
| Original panel 8051 image | 4162 bytes, `55779328f8d9de6675ac3a145f846cfc3f86aaa346136698ef4df31edc15c4dd` |
| 34410A schematic | `221f3defbc5490420bb8911f46519ae48051db6b97a4e71cd740aa08d6fe2482` |

The same 4162-byte image was verified as an exact slice of both studied PPC APP files: 34410A file offset `0x007A3EDF`, mapped `0x007B3EDF`; 34411A file offset `0x007A449F`, mapped `0x007B449F`. Both APP files and the extracted front-panel image are external evidence; none is included in the 1.2.1 release tree.

Both slices have the original panel image hash above. Image metadata at `0x1000..0x100D` is `000960001e010000000000000000`; revision `0x0009` occupies `0x1000..0x1001`. The application image contains `LCALL 0xFF03` at `CODE:0C14` and `CODE:0C21`; these are calls to an internal ROM ISP entry, not evidence that internal-ROM bytes are present in the short image.

## Historical local static exports

These historical local evidence exports and scripts retain their original byte identities. They are not redistributed, and their hashes are not claims about current publication files:

| Export | SHA-256 |
|---|---|
| `original_fp_bootloader_opcode_replay.md` | `55563900bb201e5440933872d927c9dde15bad937b9e9fd010e8d4c09d0bd922` |
| `original_fp_isp_wire_opcode_replay.md` | `d43e019e591e09eddde0377017dc869523ff73b9cd83929a664bc504eab106fa` |
| `ExportOriginalFpBootloader.java` | `44a6b3b7acf2257620f3f216df4fb33ccc391cb660d14ababad057e253def0e4` |
| `ExportOriginalFpIspWire.java` | `d5d0569baaf87e87cbb5810a7edda43839deaa0f276eca3de132cd8163d86154` |

Key 8051 runtime anchors are serial ISR `CODE:05E3`, 64-entry dispatcher `CODE:0882`, and tone table `CODE:0274`. Key PPC tables are annunciators at file `0x007B8AB0`/mapped `0x007C8AB0` and raw-key mapping at file `0x007B8F84`/mapped `0x007C8F84`. Stock-update anchors are listed in `ORIGINAL_FIRMWARE_UPDATE.md`; ASCII HEX formatting is additionally closed at PPC renderer `0x00596DB0`.

## Historical original-MCU analysis identities

| Artifact | SHA-256 / result |
|---|---|
| Historical full 8051 literal/decompiler replay | `f388e1e719c95864d75786787db6e1bb7b4f590c24acdc8276a4b6bb1c0c8e87` |
| Historical local closure trace results | `51a8b19f421b938ef4ccf8027aa16ddd766a599b180a3f0a90955a0ab700f7c0` |
| Historical local closure replay script | `71556aa81674385cdd63f38872f4c7e0ed670bcfdeb3f0d166b19b13008e94bb` |
| Historical local machine protocol extract with CRLF | `6e3a131f0067e0983077c8d71272b3013306cc00033a67d7cdf8b0ea8a9587bf` |
| Local listing extent | `CODE:0000..1041`, 71 recovered functions; extent alone does not prove every semantic claim |

The historical closure trace did not execute the compiler initializer table and its command/count/start labels required correction. Those identities are retained as an audit trail, not used as the expected bytes of corrected 1.2.1 artifacts.

## Current public artifacts

| Public artifact | SHA-256 |
|---|---|
| `derived/front_panel_protocol_extract.json` (canonical LF) | `0af8b024342dcd247d0fa593e53a9b67fefdbb6ecb328b76d4445cb36dac41c6` |
| `derived/original_mcu_trace_results.json` (corrected summary, canonical LF) | `0b1b1a97f3d0490fa379888011d86b3b56aee9ff0b94f97fdec378a43118207a` |

The public protocol extract preserves the historical extract's decoded data: all 64 dispatcher entries, five sound sequences, 85 tone-reload pairs, display objects, and key maps. Its LF bytes differ from the historical local CRLF file. The public trace summary includes 1.2.1 corrections and is not byte-identical to the historical closure output. `data/original_mcu_architecture.json` provides the corrected subsystem summary. `SHA256SUMS.txt` binds the final publication files.

The extract's historical `firmware.path` value, `derived/firmware/34410A_front_panel_firmware.bin`, records the original extraction location. It is not a packaged file path or an automatic lookup instruction. The extract is retained unchanged; firmware-backed tools require the explicit external input described below.

## Reproduction requirements

The public package contains reconstructed data, models, tests, and the [bounded firmware oracle](FIRMWARE_ORACLE.md). Ordinary public-only tests check those models and package consistency. Original-byte execution requires a separately supplied 4162-byte image via `--firmware` or `FP_ORIGINAL_FIRMWARE`, validated against the length and hash above. Missing optional evidence is reported as skipped; `FP_REQUIRE_ORIGINAL_FIRMWARE=1` makes it mandatory for a full evidence audit. An invalid supplied image fails. No tool downloads an image or searches private project directories.

Reproducing the PPC wire/update reconstruction requires the exact separately obtained APP images, their address mapping, and independent static analysis. The historical Java scripts, opcode exports, and Ghidra databases are not in this package. Their hashes identify evidence but do not replace access to it. Internal ROM implementation, peripheral timing, and bench behavior are not established by the bounded oracle.

## Method

Results were obtained by reconciling literal opcode/listing views with decompiler views on both sides of the protocol. The listing controls when representations disagree. The panel reference models implement reconstructed digital behavior without executing the original 8051. The separate bounded oracle executes selected original instruction paths when external firmware is explicitly supplied. Neither opens a UART.

## Redistribution boundary

The 1.2.1 release tree does not redistribute original front-panel or PPC APP firmware images, original manuals, schematic PDFs, full listings, or decompiler databases. Source hashes, offsets, addresses, and reconstructed tables preserve traceability. Historical tags and Git history remain unchanged and may contain the front-panel binary from earlier releases; removal from the current tree does not purge history. See `NOTICE.md`.

## Evidence classes

- `DIRECT_STATIC`: directly reconstructed from executable images;
- `SCHEMATIC_CONFIRMED`: read from the schematic without physical measurement;
- `DERIVED`: calculated from direct facts and explicitly identified;
- `OPEN`: insufficient evidence;
- `BENCH_MEASURED`: reserved for documented bench evidence.
