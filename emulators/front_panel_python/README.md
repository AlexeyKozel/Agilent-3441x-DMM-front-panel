# Original Front-Panel Python Emulator

`PanelModel` is the deterministic Python emulator of the original 34410A/34411A front-panel MCU's digital runtime behavior. It is also the reference model used by the C99 differential tests and by the PPC host emulator tests.

It models the reconstructed 9-bit parser, command replies, 150-byte framebuffer within 512-byte XRAM, 600 two-bit display cells, key-event FIFO and SRQ state, sound tables and sequences, reset behavior, echo/resynchronization, and deterministic diagnostic traffic. Normal application reset assumes P1.4 high, fills the framebuffer with `FF`, and enables the software IRQ gate. Display bytes write XRAM as they arrive and survive CMMD resynchronization; all counts follow the MCU's unchecked XRAM semantics. Diagnostic command `36` stores a raw counter and tests its previous value against 30 on each enabled loop.

The package has no third-party dependencies and does not open a serial port or access an instrument.

```python
from emulators.front_panel_python import PanelModel

panel = PanelModel()
revision_reply = panel.receive_word(0x101)
status_reply = panel.receive_word(0x105)
```

Run its tests from the repository root:

```text
python -B -m unittest -v tests/test_front_panel_python.py
```

## Validation boundary

**NOT TESTED ON REAL HARDWARE.**

The emulator has been validated only through offline unit tests, deterministic fixtures, reconstructed-protocol examples, bounded firmware checks, and differential checks against the C99 implementation. Firmware-backed checks require an explicitly supplied external image; see [FIRMWARE_ORACLE.md](../../docs/FIRMWARE_ORACLE.md). It has not been connected to a real 34410A, 34411A, original front panel, UART, reset/SRQ line, VFD, keypad, or J1102 connector. It is not an instrument driver or deployable MCU firmware.
