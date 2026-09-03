# Open Questions and Evidence Boundaries

The following items are not closed by this release:

- bench-measured J1102 levels, thresholds, edges, and timing margins;
- exact reset/power/break waveforms and power sequencing;
- absolute sound frequencies and durations until MCU and timer clocks are closed;
- original MCU package marking, package pinout, and electrode-level VFD routing;
- final continuity verification of the physical keypad matrix;
- internal bytes of the MCU ROM ISP service at `0xFF03` (the wire protocol and stock PPC host flow are statically closed);
- bench execution and timing of the stock erase/program flow;
- real-hardware validation of the FP emulator and PPC host emulator, including target ABI, UART driver behavior, timing, reset/SRQ signaling, and electrical compatibility.

These open items do not invalidate closure of the runtime byte protocol, original 8051 architecture and cooperative loop, logical renderer, included original-panel image identity, or ISP wire contract.