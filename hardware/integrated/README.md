# Integrated HP 21xx I/O schematic — initial capture

Open [HP21xx_IO.kicad_pro](HP21xx_IO.kicad_pro) in KiCad. The root drawing is
[HP21xx_IO.kicad_sch](HP21xx_IO.kicad_sch). A four-page
[PDF preview](HP21xx_IO.pdf) is saved alongside it.

This is an editable **initial capture**, not a completed electrical design or
a PCB manufacturing release. KiCad **10.0.5** opens, plots, exports a netlist
and runs ERC on the files. No prototype PCB layout or existing firmware was
changed. The supplied `IOB Proto Board` remains the mechanical reference.

## Four A3 sheets

| Drawing | Captured contents |
| --- | --- |
| FPGA root | All 144 package pins across four units; two buck regulators; SPI configuration flash and bias; shared 50 MHz oscillator/fan-out and series positions; accepted FPGA JTAG header; 21 FSMC/AUX disconnect links; FPGA status and HP/core power indicators; initial local bypassing. |
| STM32 | All 100 package pins; independent 8 MHz crystal; Schottky-OR input and third buck; HRO USB-C and ESD/sense/Rd circuitry; SD-106M logical contact map, card switches and pulls; accepted SWD header; BOOT0/DEV jumpers; HP-presence/reset gate/button; SN75185 and pendant/spare receiver translation; MCU status and power indicators. |
| HP interface | All **43 receivers**, **24 drivers**, **four hex ACT04 ICs**, per-channel resistor/diode networks; logical 86-contact HP edge numbering; power entry and PON conditioner. Driver-input pull-ups go to **+3V3_HP**. |
| Expansion | Hierarchical access to the 25 FPGA/shared nets, 25 MCU spare nets and 12 spare RS-232 nodes. Test-point symbols are logical access placeholders; physical top connector/post allocation remains open. |

The first pass has **639 symbol units / 606 annotated references**, including
non-purchased power flags and logical access test points. Accepted purchasing
identities are carried in `Manufacturer`, `MPN`, `LCSC`, `TME`, `Source` and
`BOM_Item` symbol fields. Schematic reference numbers do not replace the
functional BOM's stable item IDs.

Cross-sheet signals use explicit hierarchical labels/pins; supply names use
global power labels. The 19 FSMC wires and two AUX nets reach the expansion
sheet on the FPGA side of their disconnect links. MCU JTAG series resistors
are in the MCU branches; the external FPGA header stays on the FPGA nets.

## Validation performed

[capture_validation.json](capture_validation.json) records the latest check.
The exported KiCad netlist contains **1,665 checked connected pins**, with
**zero unintended merges of differently named design nets**. The checker
also verifies all 144 FPGA and 100 MCU package numbers, exact HP channel
counts, three regulators, 21 transport/AUX links, local bypass counts, all
four A3 sheets, and both USB-C data orientations against the HRO footprint.

The [ERC report](initial_erc.json) currently has **two errors and 17 warnings**;
none are suppressed. The errors are the unconnected pendant RS-232 receiver
input and unresolved shared UART buffer `/OE` control. Two warnings concern
the stock Spartan-6 symbol modeling the deliberately grounded HSWAPEN and
SUSPEND pins as bidirectional. The remaining warnings identify incompletely
captured signal endpoints, primarily Ethernet and service/expansion nets.
There are no connection-grid, connected-NC or nonexistent-footprint-link
violations. ERC is not clean and the design is not electrically accepted.

The per-pin comparison checks capture integrity, not transistor behavior,
reset thresholds, power-up sequencing, USB compliance, signal integrity or
physical pin numbering of connectors whose drawings remain unreviewed.

## Remaining capture work

Use [bom_capture_coverage.csv](bom_capture_coverage.csv) for every functional
BOM item's planned and currently captured reference counts. The complete
[functional BOM](../../requirements/INTEGRATED_BOARD_BOM.csv) remains the
procurement/design baseline; do not order from the partial schematic BOM.

- Capture Ethernet PHY, H1102NLT magnetics, external PHY LEDs, PHY reset,
  strap/termination/filtering and ESD/isolation circuitry. Those selected
  parts are still in the functional BOM, not silently omitted from the design.
- Close the pendant numbered contact pinout, +5 V current-limit resistor,
  protection and hardware UART `/OE` gating. No unapproved cable pin numbers
  or current limit were invented.
- Reconcile remaining bulk/bypass, series-link and protection positions from
  the coverage CSV. The first pass intentionally does not auto-place every
  speculative BOM row as a disconnected symbol.
- Verify SD-106M shell/switch common pads; GOODWORK ESD pinout; exact flash,
  crystal, oscillator, inductors and connector mechanical drawings. Blank
  footprint fields explicitly preserve work that has not been checked.
  Generic assigned footprints still need mechanical review against the exact
  manufacturer's drawings before PCB transfer.
- Finish the expansion connector/post geometry and contact numbering. The
  logical HP edge symbol is **not** a validated physical finger footprint.
- Review reset/partial-power behavior, FPGA configuration bias, PON levels,
  resistor dissipation, crystal startup, power LED sensing and HP timing.

The unshielded RJ45 choice remains MTJ-885X1 with sourcing open, with the
stocked Molex 85503-5001 recorded as a zero-quantity alternative in the BOM.
Schematic capture does not imply acceptance of that alternative.

## Files and repeatable checks

[HP21xx.kicad_sym](HP21xx.kicad_sym) is a project-local symbol library.
SN75185/CDCLVC1104 pin numbering follows the linked TI data sheets in the
design. Standard NPN, ACT04 and flash graphics are aliases with explicitly
reviewed package-number connections; manufacturer-specific electrical and
footprint checks still apply. Every sheet also embeds its used definitions,
so opening the initial drawing does not depend on the generator being run.

[scripts/kicad_capture.py](../../scripts/kicad_capture.py) generated this first
pass from the installed KiCad symbols and reviewed pin CSVs. It refuses to
overwrite existing sheets without `--force`. **Preserve manual KiCad edits
before regeneration**; this is a seed generator, not a round-trip editor.
The capture manifest and checker must be updated if subsequent manual work
changes references or nets.

From the repository root, with KiCad CLI on `PATH`:

```sh
mkdir -p build/bom-review
kicad-cli sch export netlist hardware/integrated/HP21xx_IO.kicad_sch -o build/bom-review/initial-schematic.net
kicad-cli sch erc hardware/integrated/HP21xx_IO.kicad_sch --format json -o build/bom-review/initial-erc.json
python3 scripts/check_kicad_capture.py
kicad-cli sch export pdf hardware/integrated/HP21xx_IO.kicad_sch -o hardware/integrated/HP21xx_IO.pdf
```

On this Mac the CLI is
`/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`. KiCad's local GUI
state and transient lock files are ignored in this project directory.
