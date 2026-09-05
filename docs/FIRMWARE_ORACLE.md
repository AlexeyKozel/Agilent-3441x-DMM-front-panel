# Optional original-firmware oracle

The publication does not redistribute the original firmware. The optional oracle
reads a file explicitly supplied by its user. It never downloads firmware or
searches other projects. A file must be exactly 4162 bytes and have SHA-256
`55779328f8d9de6675ac3a145f846cfc3f86aaa346136698ef4df31edc15c4dd`.
Keep that external file outside the publication directory. The publication
verifier prohibits bundled firmware dumps.

Run from the publication root:

```text
python -B tools/firmware_oracle.py --firmware /path/to/34410A_front_panel_firmware.bin
```

The command writes deterministic JSON to standard output and does not create
files. The firmware is only read. No hardware access is implemented.

To run the Python model against this independent oracle, set
`FP_ORIGINAL_FIRMWARE` to the same external file and run:

```text
python -B -m unittest discover -s tests -p "test_firmware_oracle.py"
```

Without that environment variable, the original-firmware regression class is
explicitly skipped; the input-validation tests still run. Set
`FP_REQUIRE_ORIGINAL_FIRMWARE=1` to make a missing external file an error.
A supplied unreadable file or incorrect hash is always an error, even when
firmware-backed testing is optional. A skipped oracle is not firmware validation.

## What is executed

- Reset and C initializer instructions, from `CODE:0000` until the first entry
  at `CODE:0A3B`, with a 6000-instruction bound. This includes the table at
  `CODE:04F8`, not merely the preceding RAM clear loops.
- The isolated `CODE:0EED` debounce/SRQ initializer. Small checked opcode
  windows pin the normal runtime initialization call order and relevant later
  setup. The rest of main initialization is not executed.
- Selected `0x21` inline command/count/start/store instructions, including
  per-byte XDATA writes and `DJNZ` completion, plus the `0x05` status handler.
- The `0x36` counter latch and main-loop counter window, including actual calls
  to the diagnostic key generator and four-entry FIFO enqueue routine.

The regression tests compare the model to these executed instruction results:
startup state, each display byte and reply, retained partial writes after
resynchronization, zero count, writes beyond the logical framebuffer, diagnostic
event timing in loop iterations, and FIFO/SRQ state. They do not derive expected
values from the Python model or a copied model trace.

The normal application startup branch assumes `P1.4=1`; the opaque ROM calls
through `CODE:FF03` on the alternate branch are excluded. C startup enables the
key IRQ gate and initializes the 150-byte display buffer to `FF`; the later
isolated initializer clears P1.6 and initializes debounce XDATA `0x96..0xA9` to
`82`. The remaining normal hardware-setup routines do not overwrite the IRQ gate
or display buffer in the audited image. That last statement is a bounded static
interpretation, not peripheral execution by this tool.

## Limits

This is a small instruction-window oracle, not a complete 8051 emulator. It does
not execute arbitrary interrupt scheduling, the display scan pipeline, physical
key scanning/debounce timing, sound timing, peripherals, ROM, or the PowerPC APP.
It explicitly selects the display command path and models an input SBUF latch;
UART framing/resynchronization recognition is outside these executed windows.
Nonzero out-of-framebuffer writes are compared as XDATA effects; their possible
effect on the original scanner state is outside the model. Electrical levels,
connector mapping, real baud tolerance, reset timing, and hardware compatibility
are not established by a passing test.

No reconstructed fixture substitutes for an absent original image. The public
ordinary test suite and this optional firmware-backed suite therefore establish
different, explicitly reported scopes.
