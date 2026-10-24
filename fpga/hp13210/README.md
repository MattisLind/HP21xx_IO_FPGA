# HP13210 FPGA port

The local controller starts from `hp2116_verilog/hp13210a.sv` at submodule
commit `f07b9637157b990d54c7959e7d8c0b1c27f18a61`. The user reports that the
reference passes disk diagnostics and boots RTE II in Verilator. The reference
submodule is unchanged. This initial port has directed controller tests; those
full-system diagnostics and RTE II have not yet been rerun against the port.

The first physical HP 2100S diagnostic used the wrong 15/16 select-code pair
and reported E3 on 16. On 2026-10-24 the user corrected the diagnostic to
**data 14 / command 15** (octal) and reached `E50 UNIT 0 MISSING-PRESENT NONE`.
This is consistent with the four drives starting not ready and the STM32 disk
backend still absent. If E50 was the first error, both initial channel flag
checks completed. Full physical HP bus acceptance remains pending. See the
[diagnostic analysis and small flag tests](../../diagnostics/hp13210/README.md)
for the exact sequences, hardware references and probe points.
This investigation makes no downloads or HDL changes.

## Current scope

`hp13210a_core.v` retains the reference's command/data channels, flag buffers,
control, skip and priority/interrupt behavior, status bits, attention, data
buffers, seek-record state machine, and STM32 register map. It contains no
disk image, SD-card implementation, or STM32 firmware.

`hp13210a_fpga.v` supplies the 50 MHz boundary and power-on reset. Its default
`ENABLE_STM32=0` holds the backend inactive, never drives the FSMC data bus,
and keeps backend interrupts disabled. HP flags and status checks can operate
without firmware. All four drives start not-ready; a disk read/write command
does not receive fabricated data or completion from a dummy disk.

Set `ENABLE_STM32=1` to expose the register interface to a backend. The
testbench uses a behavioral bus master for this mode; it is not STM32 code.
Future firmware must initialize drive status, service commands/data requests,
and report completion/attention.

The current carrier top enables this interface for the USB/FSMC transport test
in [firmware/stm32](../../firmware/stm32/README.md). This test firmware does not
implement the disk backend. This FSMC-enabled image was programmed into SPI
flash on 2026-10-23 after successful SRAM bring-up.

On 2026-10-24 a separate [STM32 FAT disk backend](../../firmware/stm32-disk/README.md)
was implemented against this register map. It has not been loaded: first run
the existing USB/FSMC transport test. The backend adds ready images and basic
read/write command servicing; its hardware behavior is still unverified.

## ISE adaptations

- Verilog-2001 declarations, packed four-bit drive-status vectors instead of
  SystemVerilog unpacked-array reset patterns, and localparams for seek states.
- All state has an explicit synchronous reset. The wrapper generates an
  initialized four-clock startup reset and synchronizes the external reset.
  POPIO clears the state and edge history; explicitly enabled backend IRQs
  survive POPIO as intended by the reference. Board reset disables them.
- Drive not-ready resets to `4'hf` rather than the reference's all-ready zero.
  `RESET_NOT_READY` on the core permits a different integration policy later.
- The FSMC interface uses separate input, output, and output-enable signals
  inside the core. One read mux replaces the reference's overlapping procedural
  tri-state assignments. Defined read values and reserved zero bits are tested.
  Tri-states appear only at the outermost AD pins, with immediate release on
  raw chip-select, address, write, or read control changes.
- FSMC address capture is qualified by chip select. The register read mux also
  implements attention readback at address `0x06`.
- The reference's lower FLG/IRQ outputs remain inactive; its data flag drives
  SRQ and its interrupt latch drives FLGH/IRQH. No interrupt routing was
  silently reassigned during porting.

## Clock crossings and timing limits

HP controls/data are sampled through two register stages. Control synchronizers
carry `ASYNC_REG` and `SHREG_EXTRACT=NO` attributes. FSMC controls are similarly
synchronized, with a sampled AD data path and a separate raw read-release gate.
The core consumes synchronized levels on the following clock: sequential
effects typically take 40–60 ns from a clean asynchronous input transition.

This is a provisional sampled-bus interface, not a proof of coherent capture
for arbitrarily timed multi-bit changes. Data, selection, and strobes must meet
a bundled-data protocol. The directed tests change signals off clock edges,
hold HP strobes for 173 ns in the original regression and 200 ns at four clock
phases in the HP 2100S cases. At 50 MHz, 200 ns spans ten clocks. Four further
mock-backend cases hold NE permanently active. All fourteen variants pass.
FSMC address/data setup and hold phases are roughly 180 ns with a 241 ns read
phase; these settings are not a measured minimum timing specification.
Real HP data setup/hold, response sampling, receiver/driver
delays, bus turnaround, and STM32 timing still require closure before hardware
acceptance. The former 100 MHz simulator's FSMC timings cannot be copied
unchanged and assumed valid for this 50 MHz synchronized boundary.

## Register interface retained for future firmware

Addresses in this table are the values on multiplexed AD during NADV, retained
from the behavioral reference. On the real STM32 with a 16-bit FSMC width, CPU
byte offsets are twice these values: for example AD `0x0E` is CPU `0x6000001C`.
Only the low four AD address bits are decoded; higher addresses alias.

| Address | Read | Write |
| --- | --- | --- |
| `0x00` | CSR: command IRQ bit 7, data IRQ bit 6; end of read acknowledges command IRQ | Command IRQ enable bit 8, data IRQ enable bit 9 |
| `0x02` | Command in bits 15:12, protected/defective cylinder in 9:8, seek-aborted mask in 5:2, drive in 1:0 | No state change in this reference revision |
| `0x04` | HP-to-drive word; end of read acknowledges data IRQ and advances handshake | Drive-to-HP word and data handshake |
| `0x06` | Four-bit attention mask | OR bits 3:0 into attention; triggers reference command-flag handshake |
| `0x08` | Zero | Set selected drive status bits |
| `0x0A` | Zero | Clear selected drive status bits |
| `0x0C` | `{0, cylinder[7:0], head[1:0], sector[4:0]}` | No operation |
| `0x0E` | 16-bit transport-test scratchpad | Replace all 16 bits; no disk side effects |

The scratchpad resets to zero on FPGA reset and survives HP POPIO. Directed
tests include walking ones/zeros, alternating/all-bit patterns, reset and POPIO
behavior, register isolation, and immediate AD release on read completion.

Status-mask writes use drive number in bits 15:14. Bits 12:0 select, from high
to low: seek-aborted, seeking, first-status, overrun, drive-unsafe, data-protect,
seek-check, not-ready, end-of-cylinder, address-error, flagged-cylinder,
drive-busy, data-error. The HP status word uses the reference's distinct bit
layout; it is not the status-write mask. Firmware interrupts still need their
enables written explicitly.

## Verification and build

```sh
make controller-sim
make controller-smoke
```

Simulation runs the boundary at 50 MHz both with the backend disabled and with
a mock backend enabled. It covers startup, flag buffers, STF/CLF/ENF ordering,
clear priority, unselected access, SFS/SFC, STC/CLC/CRS, PRH/IEN/SIR/IAK interrupt
behavior, not-ready status, and absence of fabricated disk completion. The
enabled-backend case adds CSR acknowledgement, IRQ enable and POPIO behavior,
data in both directions, attention accumulation, status set/clear, two-word
seek capture, and AD bus turnaround. Evidence is in `build/sim/hp13210/`.

The ISE smoke build enables the backend so the full controller is implemented,
including its read mux and I/O buffers. It runs XST, NGDBuild, MAP, PAR, TRACE,
and BitGen DRC at 20 ns. Only the clock is located at its real pin P56; other
pins are automatically placed. It deliberately generates no `.bit` file and
is not a board download. Evidence is in `build/controller/`. Internal timing
closure does not establish asynchronous bus setup/hold or output timing.

Verified on 2026-10-17: both simulation modes pass. The ISE smoke build passed
all stages and the no-bitfile DRC reported zero errors and zero warnings.
Final implementation uses 250 flip-flops, 314 LUTs, 129 slices (9%), and 83
IOBs. TRACE covers 3,480 paths with zero timing errors; minimum period is
5.635 ns, setup slack 14.365 ns, and hold slack 0.366 ns. The eight synthesis
warnings concern one unused internal signal and seven inputs already unused
by the reference; MAP removes those unused input ports. No latches are inferred.
The reference submodule remains unchanged. This smoke flow does not download
or write flash; the located carrier image below uses a separate workflow.

## Physical board integration

### Located carrier image with FSMC

`hp13210a_board.v` is the carrier bring-up top with the STM32 interface
enabled and its internal NE held active. Every one of its 89
top-level bits has a physical pin assignment. `controller_board.py` reads the
HP and STM32 workbooks and rejects missing pins, duplicate pins, direction mismatches,
and assignments to reserved flash/configuration pins. It uses P57 for HP
IOB4, P58 for IOB12, P56 for the 50 MHz clock, and P143 for the activity LED.
Either select code (`IOG & SCM & SCL`, lower or higher) starts a **100 ms pulse**.
Each channel is edge-detected independently after two-stage synchronization,
including a direct switch between channels while IOG remains asserted.
Selections arriving during a pulse share that pulse; they do not lengthen it
or queue delayed blinks. A held selection produces one pulse.

With neither channel selected, a 100 ms heartbeat starts every **two seconds**.
Every selection restarts the idle interval, including selections during an
existing LED pulse; a held selection suppresses
the automatic heartbeat. At 50 MHz the pulse lasts 5,000,000 clocks and the
idle period is 100,000,000 clocks. This indicates selection/configuration
activity, not successful disk operations. These sources replace the earlier
2 Hz heartbeat. The updated image was programmed into flash on 2026-10-23.

Flash chip select on P38 is held high after configuration. RUN drive on P138
is held high (inactive); its receiver on P139 intentionally shares the same
HP bus pin. EDT on P123 is an input and is currently ignored by the core.
The latest flash image includes the EDT and physical polarity corrections.
Historical build measurements
below describe that earlier image, not the corrected sources.
HP outputs are gated during startup, with priority passed
through while startup is held. Unconnected HP inputs receive weak inactive
biases for standalone carrier testing. STM32 AD pins are driven only during
valid read phases. NADV/NOE/NWE have weak pull-ups; IRQ/DRQ pads are not exposed.

```sh
make controller-build
make controller-program
```

The located build runs simulation, XST through TRACE, and BitGen with CCLK
startup, SPI x1, 2 MHz initial configuration clock, and unused-pin pulls disabled.
Evidence and the boot image are in `build/controller-board/`. Programming
first loads the already verified JTAG-to-SPI bridge, reads and verifies a fresh
full-flash backup under `build/controller-board/backups/`, then writes and
verifies the controller boot image and requests reconfiguration. Existing
backups, including the original erased-flash backup, are preserved. Source,
workbook, settings, and bitstream changes invalidate programming evidence.

The board wrapper inverts HP receiver inputs to restore the reference logic
levels and inverts core outputs before the external inverting drivers. Inactive
driver inputs, including RUN, are high; priority passes through during startup.
The physical board test models receiver inversion and verifies driver polarity.
External 4.7 kΩ pull-up networks are ordered but not fitted. Real bus timing
and electrical verification remain part of hardware integration.

The earlier backend-disabled located build passed on 2026-10-17:
103 flip-flops, 94 LUTs, 42 slices,
and 52 retained IOBs, all located. Unused inputs and backend logic were
optimized away. TRACE covers 1,390 paths with zero timing errors; minimum
period is 3.822 ns, setup slack 16.178 ns, and hold slack 0.392 ns. BitGen
DRC reports zero errors and zero warnings. The board-wrapper simulation and
all 16 validation tests pass.

The updated FSMC-enabled design on 2026-10-18 uses 293 flip-flops, 332 LUTs,
147 slices, and 82 retained IOBs, all located. TRACE analyzes 3,763 paths in
the 20 ns clock group, with zero timing errors, a 6.377 ns minimum period,
and 13.623 ns setup slack. BitGen generated the SPI boot image. Asynchronous
pin paths are reported separately; these results do not establish external
HP or STM32 bus setup/hold requirements. The updated design has not been
tested on either physical bus at that point. It was later programmed into
flash with the updated LED behavior on 2026-10-23.

The located FPGA-only controller image was programmed into the W25Q16JV on
2026-10-17. A fresh full-flash backup of the prior blink image was saved and
verified first. Programming's automatic verify and a second independent
readback check both passed, with SR1/SR2/SR3 unchanged at `00/02/60`.
JTAG reconfiguration from flash completed. The build/backup/program receipts
are under `build/controller-board/`. The user confirmed the new 2 Hz heartbeat
after power cycling without a download; controller-image cold boot is verified.

The user confirmed both receivers and drivers invert voltage. The
[receiver/driver schematic](https://github.com/MattisLind/HP21xxReceiverDriver/blob/c591b1f920abc80e3fff952abd2bcf83055bdcd6/HP21xxReceiverDriver.kicad_sch)
was inspected at commit `c591b1f920abc80e3fff952abd2bcf83055bdcd6`. Receiver
RO1 has a 220-ohm collector pull-up to its 3.3 V rail; the driver uses a
74ACT04 and transistor output stage. Driver DI1 has a 2-kohm pull-up R49 to
`PLUS5D` (the other five channels use R50–R54). The user confirmed this is a
design error and has removed the 5 V input pull-ups. Five 4.7 kΩ SIL resistor
networks are on order for 3.3 V pull-ups. Fit the new bias and verify the voltage
presented to a high-impedance FPGA pin before connecting the HP bus. The external
receiver/driver repository was not modified.

The controller uses logical asserted/not-asserted signals, not connector
voltages. External inversion must be combined with each HP signal's asserted
level when making the physical wrapper; do not insert another inversion solely
because the external circuit is inverting. The initial host is HP 2100S;
physical signal levels and timing still need hardware validation.

The spreadsheets were updated with user authorization on 2026-10-17:

| HP output | Connector pin | Driver channel | FPGA pin |
| --- | --- | --- | --- |
| IOB4 | 42 | B2DO4 | P57, previously blank |
| IOB12 | 57 | A4DO2 | P58, moved from P70 |

P70 remains dedicated to flash CCLK. The STM32 sheet now reserves P57/P58 for
these HP outputs; neither was assigned an STM32 function. P57 is therefore no
longer an optional LED pin; use the verified LED on P143. Original workbooks
are retained in `build/pin-mapping-before-13210/`.

The HP workbook now routes EDT from HP bus pin 62 through receiver B5RI1
to FPGA P123. B5RI1 was unassigned; the former A4DO5 driver is now spare.
EDT is generated by the computer/DCPC at the end of a transfer.
See the [HP interfacing guide](https://www.bitsavers.org/pdf/hp/21MX/02109-90006_21MX_M-Series_and_E-Series_IO_Interfacing_Guide_197707.pdf),
section 4, DCPC timing. The reference input direction was correct.

The STM32 sheet now names PB7/P75 `FSMC_NL`/NADV. IRQ and DMA request are
deferred, with their pins reserved. Initial firmware will poll registers;
the reference testbench does use `stm32_irq`. With one FSMC device, no external
NE pin is required: hold internal NE active in the enabled backend and keep
NADV/NOE/NWE idle high, including during STM32 reset. The current carrier source
enables FSMC with this wiring and is now programmed into SPI flash.
Initial STM32 timing and USB pattern-test instructions are in the
[firmware guide](../../firmware/stm32/README.md). Physical FSMC timing needs
verification independently of the HP bus's 200 ns pulse interval.

On 2026-10-23 the user confirmed the latest SRAM image works. A fresh full
2 MiB backup of the older flash image was saved and verified, then the latest
bitstream was programmed and verified twice. Flash status stayed `00/02/60`;
reload from flash was requested successfully. The receipt is
`build/controller-board/programmed.json`. The user confirmed on 2026-10-23
that the new 100 ms / two-second idle pattern returns after power cycling;
persistent boot of this revision is accepted.
See [outstanding questions](../../requirements/OUTSTANDING_QUESTIONS.md).
