# Physical Interface and J1102

## 1. Source and evidence status

The pinout was read from page 13 of `Agilent_34410A_6.5_digit_DMM_Schematics.pdf`, SHA-256 `221f3defbc5490420bb8911f46519ae48051db6b97a4e71cd740aa08d6fe2482`. Status is `SCHEMATIC_CONFIRMED`, not `BENCH_MEASURED`.

## 2. J1102 pinout

| Pin | Net | Class | Note |
|---:|---|---|---|
| 1 | DCOM | common | digital common |
| 2 | FILP | VFD supply | not 3.3 V logic |
| 3 | FILN | VFD supply | not 3.3 V logic |
| 4 | +3.3V_ER | logic supply | nominal 3.3 V domain |
| 5 | +12V_UNREG | supply | not 3.3 V logic |
| 6 | FP_SIN | logic signal | `+3.3V_ER` domain in schematic |
| 7 | DCOM | common | digital common |
| 8 | FP_SOUT | logic signal | `+3.3V_ER` domain in schematic |
| 9 | PWR_FAIL* | logic signal | active-low name; connector polarity not measured |
| 10 | FP_SRQ* | logic signal | active-low event ready |
| 11 | FP_RST* | logic signal | active-low reset |
| 12 | DCOM | common | digital common |

The schematic powers surrounding LVC logic, including 74LVC14 and SN74LVC2G157, from `+3.3V_ER` and exposes the same rail on J1102. The nominal interface logic domain is therefore 3.3 V. This does not establish measured thresholds, amplitudes, or edge quality.

## 3. Protocol directions

Schematic names `FP_SIN` and `FP_SOUT` should be assigned a physical driver direction only after trace or measurement confirmation. At the application level, one stream travels PPC-to-panel and uses the ninth bit for commands, while panel-to-PPC replies use ninth bit zero. This publication does not convert logical protocol direction into an unverified electrical driver claim.

## 4. Unmeasured electrical properties

The following remain unmeasured on an actual unit: continuity from every J1102 pin to the named stock node; idle and active levels of `FP_SIN`, `FP_SOUT`, `FP_SRQ*`, `FP_RST*`, and `PWR_FAIL*`; sequencing of `+3.3V_ER`, `+12V_UNREG`, and `FILP/FILN`; reset waveform and initial SRQ state; and signal quality at 625000 bit/s.

Until those measurements exist, no actual thresholds, edge rates, or timing margins are claimed.