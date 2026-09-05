# Stock Original Front-Panel Firmware Update

Specification version: `1.2.1`, 2026-09-05.

## 1. Scope

This document covers only the manufacturer-implemented update path for the original Agilent 34410A/34411A front panel: the 8051 application image embedded in the PPC APP, entry of the original panel into ISP, and records used by the PPC to drive the MCU ROM ISP service.

The conclusions are `DIRECT_STATIC`: functions, constants, and ordering were recovered from exact PPC and 8051 executable images. No bench update was executed. This is not a service reflashing procedure.

## 2. Original panel image in the PPC APP

The same original 8051 image occurs in both studied APP files:

| Model | File offset | Mapped address | Length | SHA-256 |
|---|---:|---:|---:|---|
| 34410A | `0x007A3EDF` | `0x007B3EDF` | 4162 | `55779328f8d9de6675ac3a145f846cfc3f86aaa346136698ef4df31edc15c4dd` |
| 34411A | `0x007A449F` | `0x007B449F` | 4162 | same |

Both slices are byte-identical to the studied 4162-byte front-panel application image. This release tree does not include that binary; its length and SHA-256 identify external evidence. Metadata at `0x1000..0x100D` is `00 09 60 00 1E 01 00 00 00 00 00 00 00 00`; revision at `0x1000..0x1001` is `0x0009`.

The PPC descriptor `PTR_DAT_008EA294`/`_DAT_008EA298` supplies the image pointer and length. `updateFrontpanel()` checks image availability and panel status/compatibility, then calls `Frontpanel::updateFirmware()` with that pair.

## 3. Application image versus internal ROM ISP

The 4162-byte file is the original panel application image. It contains two `LCALL 0xFF03` instructions:

| CODE offset | Immediate arguments before call |
|---:|---|
| `0x0C14` | `A=0x02`, `R5=0x01`, `R7=0x03` |
| `0x0C21` | `A=0x02`, `R5=0x63`, `R7=0x00` |

`0xFF03` is an entry into the MCU's internal ROM ISP service. The application image ends below that address, so internal ROM implementation bytes must not be attributed to that image. The PPC APP contains enough evidence to reconstruct the stock host's wire requests, response acceptance, and update sequence without those ROM bytes.

## 4. Entering programming mode

The stock PPC sequence:

1. locks and clears the panel UART channel;
2. selects DOWN mode (`ioctl 0x5004`) at 7200 bit/s;
3. controls reset/break on the original panel;
4. performs autobaud with three `0x55` transactions; accepted echo is `U` or `u`;
5. transmits ASCII HEX ISP records;
6. resets the panel, restores the saved UART mode and baud rate, waits 1000 ms, and returns to runtime.

Runtime 625000/9-bit and programming 7200/DOWN are distinct modes of the stock channel.

## 5. ISP record format

The PPC builds a NUL-terminated ASCII string:

```text
:LLAAAATT[DD...]CC
```

`LL` is the data-byte count, `AAAA` is a big-endian 16-bit address, `TT` is the record type, `DD` contains data bytes, and `CC` is the low byte of the two's-complement negative sum of all preceding binary fields. Hex digits are uppercase. The generator adds no CR/LF to the transmitted record.

For writes, the host requires an exact echo followed by the three bytes `2E 0D 0A` (period, carriage return, line feed). For reads, two ASCII hex digits containing the read byte occur after the echo and before `2E 0D 0A`.

| Response | Meaning |
|---|---|
| `2E 0D 0A` | success |
| `X...` | checksum error |
| `R...` | programming error |
| other | invalid module response |

An echo mismatch, wrong response length, timeout, or serial error fails the operation.

## 6. LPC932 records

| Operation | `TT` | `AAAA` | Data |
|---|---:|---:|---|
| program code data | `00` | destination | 1..32 bytes in stock flow |
| program UCFG | `02` | `0000` | `00 value` |
| program boot vector | `02` | `0000` | `02 value` |
| program status byte | `02` | `0000` | `03 value` |
| program security byte N | `02` | `0000` | `(08+N) value`, N=0..7 |
| read UCFG | `03` | `0000` | `00` |
| read boot vector | `03` | `0000` | `02` |
| read status byte | `03` | `0000` | `03` |
| read security byte N | `03` | `0000` | `08+N`, N=0..7 |
| read manufacturer ID | `03` | `0000` | `10` |
| read device ID byte 1/2 | `03` | `0000` | `11` / `12` |
| erase 64-byte page | `04` | `0000` | `00 addr_hi addr_lo` |
| erase 1024-byte sector | `04` | `0000` | `01 addr_hi addr_lo` |

`genDataReadRec` in the studied PPC APP is a stub returning zero; arbitrary code-byte reads are not used by the stock update flow.

## 7. Stock update order

`updateRawBytes()` implements a fail-stop sequence:

1. `startProgramming()` and autobaud;
2. read two device-ID bytes and accept a supported LPC932 variant;
3. read boot vector, status byte, and UCFG;
4. set programming status;
5. read boot vector/status/UCFG again;
6. for each sector N=0..6, clear security byte N and erase the sector at `N*0x0400` (`0x0000,0x0400,...,0x1800`);
7. read and report boot vector/status/UCFG again, validating the responses;
8. program the image in 32-byte blocks plus the final partial block;
9. restore boot vector/UCFG/status for application startup;
10. read and report final boot vector/status/UCFG, validating the responses;
11. `stopProgramming()` and restore runtime UART operation.

Any record-generation, communication, or response error aborts the programming chain. These configuration read helpers validate transport, echo, length, and response syntax; they do not compare the read configuration values against expected values. Device-ID comparison is a separate explicit gate. The described stock sequence does not establish semantic verification of final configuration or bench success.

## 8. Evidence anchors

Key PPC anchors: `updateFrontpanel 0x004E2B14`, `UpdateFp8051::updateRawBytes 0x0035F00C`, `initUartForProgramming 0x0035F664`, `startProgramming 0x0035F9DC`, `stopProgramming 0x0035F890`, `programRawBytes 0x003601BC`, `eraseChip 0x003603DC`, `Update8051::processCommWrite 0x003638B0`, `Update8051::processCommReadByte 0x00363AD8`, `Isp8051::genHexRecord 0x00367074`, and ASCII HEX renderer `0x00596DB0`.

The exact machine-readable facts are in `data/original_firmware_update.json`.
