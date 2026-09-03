# Agilent 34410A/34411A Original Front-Panel Runtime Protocol

Specification version: `1.0.0`, 2026-09-03.

## 1. Scope and evidence status

This document specifies the application protocol between the 34410A/34411A PPC software and the original front-panel 8051 firmware. MCU startup, main loop, ISR, and peripheral mechanisms are documented in `ORIGINAL_MCU_INTERNALS.md`. The command state machine, command set, display model, key events, and host transaction sequence are direct static-reconstruction results (`DIRECT_STATIC`).

The J1102 pinout and assignment of the logic circuits to `+3.3V_ER` are schematic-confirmed, not bench-measured. See `PHYSICAL_INTERFACE.md`.

## 2. UART and framing

| Parameter | Value |
|---|---|
| Runtime rate | 625000 bit/s |
| Data | 9 bits |
| Input ninth bit | 1 = command/immediate resynchronization; 0 = DATA |
| Panel reply ninth bit | Always 0 in the studied runtime image |
| Checksum, escaping, delimiter | None |
| Multi-byte revision | Big-endian |

The stock PPC normally sends a complete packet in DATA mode. This is valid while the parser is idle/completed. Any input byte with the ninth bit set immediately abandons an incomplete payload or echo stream and begins a new command. The stock recovery operation sends `0x05` in CMMD mode.

| Driver mode | ioctl | Purpose |
|---|---:|---|
| DATA | `0x5002` | transmit ninth bit 0 |
| CMMD | `0x5001` | transmit ninth bit 1 |
| DOWN | `0x5004` | download/programming; not runtime |

Programming uses 7200 bit/s. The stock ISP protocol and firmware-update flow are documented in `ORIGINAL_FIRMWARE_UPDATE.md`. The application image calls internal MCU ROM entry `0xFF03`; that ROM implementation is not contained in the image.

## 3. Parser state and host transaction

| State | Meaning |
|---:|---|
| `0x00` | payload/stream reception in progress |
| `0x01` | idle or successful completion |
| `0x81` | reject, empty dequeue, or failed result |

The PPC accepts success only when `(status & 0x85) == 0x01`. `GET_STATUS` returns the previous state and then sets it to `0x01`. Host-wrapper value `0x80` after a failed status query is not an ordinary 8051 response.

Normal transaction:

1. select DATA at 625000 bit/s and flush the channel;
2. write the command and its fixed or declared payload as one buffer;
3. read the required immediate reply;
4. send CMMD `0x05`;
5. read one status byte;
6. apply the success mask.

## 4. Complete implemented command set

The dispatcher has 64 entries for `0x00..0x3F`; values `>=0x40` reject immediately. Only the following commands are implemented. Every other opcode returns `0x81`.

| Cmd | Name | Payload after cmd | Immediate reply | Final state | Handler |
|---:|---|---|---|---:|---:|
| `01` | GET_REVISION | none | `00 09` | `01` | `0F44` |
| `03` | GET_ID | none | `1A` | `01` | `0FE6` |
| `05` | GET_STATUS | none | previous state | then `01` | `0FEF` |
| `12` | GENERATE_SOUND | duration, tone | `01` | `01` | `0C88` |
| `13` | BEEP | none | `01` | `01` | `0F2F` |
| `14` | CLICK | none | `01` | `01` | `0FAE` |
| `15` | DEQUEUE_KEY_EVENT | none | event or `FF` | `01`/`81` | `0F93` |
| `21` | WRITE_DISPLAY | count, start, data[count] | `01` | `01` | ISR inline |
| `31` | PLAY_SOUND_SEQUENCE | sequence | `01` | `01` | `0E5D` |
| `32` | ENABLE_BREAK_DETECT | none | `01` | `01` | `0F66` |
| `33` | DISABLE_BREAK_DETECT | none | `01` | `01` | `0FBA` |
| `34` | PROTOCOL_ECHO | stream | every stream byte | `00` | `0EA9` |
| `36` | DIAGNOSTIC_KEY_TRAFFIC | enable | `01` | `01` | `0E77` |
| `38` | SET_KEY_IRQ_ENABLE | enable | `01` | `01` | `0DC9` |
| `3A` | FLUSH_KEY_FIFO | none | `01` | `01` | `0FC6` |

`0x16` and `0x35` have distinct table targets but reach the same `0x81` rejection.

## 5. Command semantics

### `0x01 GET_REVISION`, `0x03 GET_ID`, and `0x05 GET_STATUS`

`01` replies `00 09`; revision is `0x0009`. `03` replies `1A`. `05`, normally sent as CMMD, returns the previous state and resets the parser to `0x01`.

### `0x12 GENERATE_SOUND`

Packet: `12 duration_selector tone_index`. Selectors below 3 are used directly. A selector of 3 or greater selects duration 2 and sets repeat count to `selector-3`. Tone 0 disables generation; tone is clamped to `0x54`; values 1..84 select exact timer-reload pairs from the JSON table. Reply is `01`. Reload values are not converted to hertz without a confirmed oscillator/timer clock.

### `0x13 BEEP` and `0x14 CLICK`

Start fixed built-in sounds and reply `01`.

### `0x15 DEQUEUE_KEY_EVENT`

A non-empty FIFO returns one event byte and state `01`. An empty FIFO returns `FF` and sets `0x81`, so the following stock status check fails.

### `0x21 WRITE_DISPLAY`

```text
21 count start data[0] ... data[count-1]
```

The stock PPC permits `0<=start<=0x95`, `count>=1`, and `start+count-1<=0x95`. A full refresh is `21 96 00` followed by 150 bytes. Normal redraws send the smallest continuous dirty span.

The 8051 does not bounds-check the framebuffer. With `count=0`, the original `DJNZ` behavior produces exactly 256 XRAM writes before completion. This is documented original behavior outside stock PPC-generated packets.

### `0x31 PLAY_SOUND_SEQUENCE`

IDs 1..5 select ROM sequences containing 13, 8, 24, 31, and 37 `(duration_selector,tone_index)` pairs. Other IDs start nothing but still complete successfully. Exact pairs are in the derived JSON.

### `0x32` and `0x33`

Enable or disable UART/break-detect SFR behavior and reply `01`.

### `0x34 PROTOCOL_ECHO`

The parser remains in state `0x00`; there is no initial ACK. Each following DATA byte is returned unchanged. Any CMMD command exits the stream, normally `0x05`, which returns the prior `0x00` and restores idle.

### `0x36 DIAGNOSTIC_KEY_TRAFFIC`

`36 enable`; nonzero enables synthetic press/release pairs for raw IDs 0..19 after approximately 30 main-loop iterations. That interval is not a physical time unit. Reply is `01`.

### `0x38 SET_KEY_IRQ_ENABLE` and `0x3A FLUSH_KEY_FIFO`

`38 00` disables event signaling and forces `FP_SRQ*` inactive; nonzero enables it and makes `FP_SRQ*` active for a non-empty FIFO. `3A` empties the FIFO and deactivates `FP_SRQ*`. Both reply `01`.

## 6. Display

The framebuffer is 150 bytes containing 600 two-bit cells:

```text
byte_index = n >> 2
n&3 = 0 -> bits 7:6; 1 -> 5:4; 2 -> 3:2; 3 -> 1:0
```

| Code | Meaning |
|---:|---|
| `00` | off |
| `01` | dim/half |
| `10` | flash |
| `11` | full |

The main row has 12 character positions and the secondary row has 18. Each character has 17 logical segments:

```text
cell = BASE + 40*(position//2) + (position&1) + 2*segment
MAIN BASE = 5
SECONDARY BASE = 245
segment = 0..16
```

| Object | Name | Cell | Object | Name | Cell |
|---:|---|---:|---:|---|---:|
| `C8` | SAMPLE | 39 | `CA` | HI_Z | 0 |
| `CC` | OCOMP | 1 | `CF` | MAN_RNG | 40 |
| `D6` | TRIG | 41 | `DC` | HOLD | 80 |
| `CD` | REMOTE | 81 | `CE` | ERROR | 120 |
| `D1` | NULL | 121 | `D4` | SHIFT | 160 |
| `DA` | MATH | 161 | `D8` | STATS | 200 |
| `D9` | LIMITS | 201 | `CB` | 4W | 202 |
| `D2` | CONT | 203 | `D3` | DIODE | 204 |
| `D7` | REAR | 239 | `DD` | LEFT | 279 |
| `DE` | RIGHT | 599 | | | |

## 7. Keypad

Five active-low rows are `P2.0,P2.1,P2.4,P2.6,P2.7`; four active-low columns are `P0.0..P0.3`. `raw_id=row+5*column`. Three consecutive pressed samples create a press event; three released samples create a release event. Auto-repeat is performed by the PPC, not the panel.

The FIFO holds four events and drops a new event when full:

```text
bit 7    startup-held marker on the first press
bit 6    1 press, 0 release
bits 5:0 raw key ID
```

| Key | RAW | PPC | SHIFT |
|---|---:|---:|---|
| DCV | `00` | `04` | DCI |
| ACV | `0A` | `05` | ACI |
| 2W | `01` | `06` | 4W |
| 2ND DISP | `0B` | `13` | RESET |
| DATA LOG | `02` | `1A` | UTILITY |
| EXIT | `0C` | `0C` | AUTO RNG |
| FREQ | `05` | `08` | CAP |
| CONT | `0F` | `09` | DIODE |
| CONFIG | `06` | `0B` | TEMP |
| NULL | `10` | `19` | MATH |
| TRIGGER | `07` | `15` | AUTO TRIG |
| SHIFT | `11` | `0A` | LOCAL |
| UP | `03` | `10` | - |
| DOWN | `08` | `11` | - |
| LEFT | `04` | `0E` | - |
| RIGHT | `0D` | `0F` | - |
| ENTER | `09` | `0D` | - |

Raw IDs `0E`, `12`, and `13` do not produce PPC events. Raw `3F` is a special system/error input rather than a physical key and maps to PPC `3F`.

## 8. Reproducibility

The offline tests cover all implemented and rejected opcodes, resynchronization, echo, status transitions, display boundaries and two-bit cells, the original zero-count edge case, key mapping/FIFO/SRQ behavior, sound bounds, annunciators, and deterministic traces. Machine-readable command, key, annunciator, pinout, and extracted firmware tables are authoritative companions to this document.