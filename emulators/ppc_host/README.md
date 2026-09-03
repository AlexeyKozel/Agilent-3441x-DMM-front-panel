# Offline PPC Host Emulator

`PpcHostEmulator` models the stock PPC-side transaction wrapper for the
original 34410A/34411A front panel. It sends ordinary packet bytes with the
ninth bit clear, terminates a transaction with CMMD `0x05`, and applies the
recovered success test `(status & 0x85) == 0x01`.

Implemented host behaviors include revision reads, fixed and variable packets,
display-span validation, key dequeue/IRQ control, streaming echo, reply-length
checks, and CMMD resynchronization after an incomplete payload.

The endpoint is deliberately abstract. The included tests connect it to the
Python `emulators.front_panel_python.PanelModel`; no serial port is opened.

## Hardware status

**NOT TESTED ON REAL HARDWARE.**

This code has not been connected to a real 34410A, 34411A, original front
panel, UART, reset line, or J1102 connector. Passing offline tests does not
establish baud-rate generation, driver ioctl compatibility, reset timing,
electrical levels, signal integrity, or safe operation on an instrument.

## Example

```python
from emulators.ppc_host import PpcHostEmulator
from emulators.front_panel_python import PanelModel

panel = PanelModel()
host = PpcHostEmulator(panel)
assert host.get_revision() == 0x0009
assert host.write_display(0, b"\x00").success
```
