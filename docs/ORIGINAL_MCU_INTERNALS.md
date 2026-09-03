# Original Front-Panel 8051 MCU Internals

Specification version: `1.1.0`, 2026-09-03.

## 1. Purpose and evidence boundary

This document describes the original Agilent 34410A/34411A front-panel 8051 firmware: startup, memory, cooperative main loop, UART parser, VFD refresh, keypad, FIFO/SRQ, sound, and calls into the MCU ROM ISP service. It complements `PROTOCOL.md` and `ORIGINAL_FIRMWARE_UPDATE.md`.

The exact basis is the included 4162-byte image with SHA-256 `55779328f8d9de6675ac3a145f846cfc3f86aaa346136698ef4df31edc15c4dd`. The literal listing covers `CODE:0000..1041`; 71 functions were recovered. Decompiler output was navigation aid only; literal opcodes and deterministic traces take precedence.

The host class name `Isp8051lpc932` and accepted PPC device IDs `0xDD05`/`0xDD1F` bind the stock update path to the LPC932 family. The package marking and physical package pinout of the installed device remain unconfirmed.

## 2. Program-image map

| Area/anchor | Purpose |
|---|---|
| `CODE:0000` | reset vector: `LJMP 0x0766` |
| `CODE:0274` | 85 tone-reload pairs |
| `CODE:031E,0338,0348,0378,03B6` | five sound-sequence tables |
| `CODE:0400` | cooperative sound-sequence worker |
| `CODE:05E3` | UART receive ISR/parser |
| `CODE:0766` | runtime startup, memory initialization, and main loop |
| `CODE:0800` | tone/duration start |
| `CODE:0882` | 64-entry command dispatch table |
| `CODE:0902,096D,0AEB,0C5B` | VFD serial/blanking refresh workers |
| `CODE:0A3B` | post-initialization entry and main loop |
| `CODE:0B42` | one keypad-row scan |
| `CODE:0B84` | UART peripheral setup |
| `CODE:0C0A` | two calls to ROM service `0xFF03` |
| `CODE:0C2A` | sound timer/interrupt worker |
| `CODE:0E06` | enqueue key event |
| `CODE:0EED` | reset key state and `P1.6` |
| `CODE:0F44..1035` | command handlers and reject paths |
| `CODE:1000..100D` | metadata; revision `0x0009` |

## 3. Reset and initialization

The startup trace is `0000 -> 0766 -> 07BB -> 0A3B`. Startup:

1. clears internal RAM and the first 512 bytes of XRAM;
2. sets `SP=0x4F` and processes the compiler initialization table;
3. initializes ports/SFRs (`P0=0x7F`, `P1=0xDF`, `P2=0xF7`, `P3=0x00`), timer/counter blocks, VFD serial interface, and UART;
4. calls `0CDD`, `0EED`, `005E`, and `0F84`;
5. enables interrupts and enters the infinite cooperative loop.

`0EED` first executes `CLR P1.6`, fills the 20 debounce bytes at `XRAM:0096..00A9` with `0x82`, and clears the current key index. Thus, after reset initialization, `FP_SRQ*` is low regardless of the software key-IRQ gate. This is a digital-code conclusion; electrical interpretation remains bounded by `PHYSICAL_INTERFACE.md`.

A particular startup state on `P1.4` enters `0C0A`, which performs two `LCALL 0xFF03` operations with the argument sets documented in the update document. Internal ROM bytes at `0xFF03` are not present in this application image.

## 4. Cooperative main loop

Every iteration:

1. calls display-refresh step `0A93`;
2. every fourth pass calls `0B42` to scan one of five key rows;
3. when diagnostic traffic is enabled, generates the next synthetic press/release pair for raw ID 0..19 after 30 passes;
4. calls empty hook `103F`;
5. advances active sound sequence worker `0400`.

Display and keypad work are sliced across iterations. Loop counts are not physical time units without a confirmed MCU/timer clock.

## 5. Memory and state

| Address | Role |
|---:|---|
| `IRAM:21,22` | display-refresh counters |
| `IRAM:2B,2C` | VFD shift/mask state |
| `IRAM:2D` | current keypad row 0..4 |
| `IRAM:2E` | diagnostic raw key ID 0..19 |
| `IRAM:30..33` | four-byte key-event FIFO |
| `IRAM:34` | FIFO write counter |
| `IRAM:35` | FIFO read counter |
| `IRAM:36` | key IRQ/SRQ software gate |
| `IRAM:37` | current command opcode |
| `IRAM:38` | payload/parser phase |
| `IRAM:39` | display-byte count |
| `IRAM:3A,3B` | command arguments/sound selectors |
| `IRAM:3C` | protocol state/result |
| `IRAM:42` | keypad-scan divider |
| `IRAM:43` | diagnostic-traffic counter |
| `XRAM:0000..0095` | 150-byte packed display framebuffer |
| `XRAM:0096..00A9` | 20 debounce/startup-held state bytes |

The packed framebuffer contains 600 two-bit cells. Exact rendering, character positions, and annunciators are specified in `PROTOCOL.md`.

## 6. UART ISR and parser

`CODE:05E3` handles `RI`, reads `SBUF` and `RB8`. If the parser is idle or `RB8=1`, the byte becomes a new command. Opcodes below `0x40` select from the 64-entry table at `CODE:0882`; all others reject.

Consequently, `RB8=1` performs immediate CMMD resynchronization from incomplete payloads and echo. Ordinary runtime replies use `TB8=0`: setup contains `CLR TB8` at `CODE:0B95`, and no `SETB TB8` occurs in the exact image.

Most handlers use a small state machine in `IRAM:38`: entry sets `IRAM:3C` to busy `0x00`, later invocations consume payload, and completion transmits ACK `0x01` through `SBUF` and sets state `0x01`. Reject paths transmit and store `0x81`. `GET_STATUS` transmits the old state and then resets it to `0x01`.

`WRITE_DISPLAY 0x21` is implemented inline in the ISR. After `count,start`, each byte is stored by `MOVX @DPTR,A`. With `count=0`, `DJNZ` causes exactly 256 writes before the parser completes. Exact-opcode replay confirms this edge case.

## 7. VFD/display engine

`0A93` cycles through `096D`, `0902`, and `0C5B`. These workers extract two-bit states from the 150-byte framebuffer, assemble nibble/shift data (`0C28` swaps nibbles), transmit inverted serial bytes through `RXDAT/EPCON`, generate latch/strobe sequences in `0DE8`/`0ED7`, and process blanking slots and display counters.

This closes the digital origin of every cell and the multiplex-refresh mechanism. Electrode-level VFD routing, absolute refresh rate, analog brightness, and flash cadence in seconds remain outside the static evidence.

## 8. Keypad, debounce, FIFO, and SRQ

`0B42` activates one of five active-low rows `P2.0,P2.1,P2.4,P2.6,P2.7` and reads active-low columns `P0.0..P0.3`. Raw ID is `row + 5*column`.

Each raw ID uses `XRAM:0096+id`. Three consecutive pressed samples raise the low counter to 3, set pressed flag bit 6, and emit a press event. Three released samples reduce the counter to zero, clear the flag, and emit a release event. Reset value `0x82` includes startup marker bit 7, retained only for the first detected startup-held key.

An event byte contains startup-held in bit 7, press/release in bit 6, and raw ID in bits 5:0. `0E06` enqueues into `IRAM:30..33`; a fifth event is dropped. With the gate enabled, a non-empty queue drives `P1.6` low. `0D06` returns a FIFO byte or `0xFF`; removing the final event drives `P1.6` high. `1029` flushes the queue and also drives `P1.6` high.

## 9. Sound engine

Tone handling uses `CODE:0800`, timer/PCA state, and output bit `P1.4`. Tone 0 disables generation; values above `0x54` are clamped. Duration selectors 0..2 select one of three timer pairs; values of 3 or greater use selector 2 and repeat count `selector-3`.

The image contains 85 exact tone-reload pairs and five sequences of 13, 8, 24, 31, and 37 pairs. `BEEP` and `CLICK` use fixed settings. `PLAY_SOUND_SEQUENCE` selects a table and `0400` advances it without blocking display/key work. All pairs are published in `derived/front_panel_protocol_extract.json`. No conversion to hertz or seconds is claimed without clock closure.

## 10. Break, diagnostic, and other paths

- `0x32` enables break-detect UART/FIE configuration;
- `0x33` disables the corresponding enable bit;
- `0x34` stays in state `0x00` and returns every DATA byte;
- `0x36` controls the synthetic key generator;
- `0x38` controls the key IRQ gate and immediately recomputes `P1.6`;
- `0x3A` synchronizes FIFO counters and releases SRQ;
- no confirmed logical binding of `PWR_FAIL*` to an 8051 port bit was found in the scoped image.

## 11. Published verification material

The repository contains the exact application image, complete command/tone/sound/display/key extract, closure traces for reset, `0x21/count=0`, and reply TB8, the architecture map, all 71 recovered function entries, and a deterministic offline reference model with tests. A full disassembly and decompiler database are not included.

## 12. Open boundaries

Static reconstruction does not prove the installed MCU's marking/package/pinout, actual J1102 levels and timing, absolute clock-derived frequencies, electrode-level VFD routing and analog brightness, or bench execution of the update flow.