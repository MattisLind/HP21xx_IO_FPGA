# Outstanding questions

## Q-01: SPI flash auxiliary pins and boot-mode straps

Status: resolved by the user's hardware inspection, reported on 2026-10-17.
Originally deferred on 2026-10-16 pending powered-down inspection.

- [x] Winbond pin 3 (IO2 / /WP): not connected (NC).
- [x] Winbond pin 7 (IO3 / /HOLD): not connected (NC).
- [x] FPGA P60 (M1): pull-down, selecting low.
- [x] FPGA P69 (M0): pull-up, selecting high.

The mode straps select Master Serial/SPI (`M[1:0]=01`). The flash IQ variant
defaults to QE=1, which disables /WP and /HOLD, so NC on pins 3/7 does not
require adding quad-data connections for the initial x1 SPI test. Flash status
readback has confirmed QE=1; do not clear it with these pins unconnected.
Flash identification, backup, and programming have been verified as described
in the flash guide. The flash now contains the verified
blink boot image, and the user has confirmed independent power-cycle boot.

See the [flash bring-up guide](../toolchain/FLASH.md) for the reported SPI
connections, remaining hardware checks, and proposed programming procedure.

## Q-02: Confirm automatic blink after power cycling

Status: resolved by the user's power-cycle test on 2026-10-17.

- [x] Power the FPGA carrier off and back on, wait a few seconds, and confirm
  that the LED starts blinking without running an SRAM download command.

Bridge build, flash identification, original 2 MiB backup and verification,
blink boot image programming, and two readback checks have passed. The FPGA
has also received a JTAG reconfiguration command. The user confirmed that the
LED resumed blinking after powering the carrier off and on without a download.
Persistent blink configuration is accepted.

The user also confirmed blinking after the earlier JTAG-triggered reload.

## Q-03: HP bus wiring and physical interface

Status: partly resolved on 2026-10-17; hardware timing and integration pending.

- [x] Both receiver and driver invert voltage. Reference circuit:
  [HP21xxReceiverDriver](https://github.com/MattisLind/HP21xxReceiverDriver/tree/c591b1f920abc80e3fff952abd2bcf83055bdcd6).
- [x] Resolve the missing HP IOB4 pin and IOB12/flash-CCLK overlap. With the
  user's authorization, the HP sheet now assigns IOB4 to P57 and IOB12 to P58.
  The STM32 sheet reserves these formerly unassigned pins for the HP bus.
- [x] The user confirmed R49–R54 pulling the driver DI inputs to +5 V is an
  error in the receiver/driver design.
- [x] The user removed the driver modules' +5 V input pull-ups.
- [x] The user confirms the HP bus defaults low at approximately -2 V;
  high at a driver DI input produces the inactive low bus level. Pull-ups
  are therefore the desired idle bias for these driver inputs.
- [ ] Fit the planned 4.7 kΩ pull-ups to 3.3 V. On 2026-10-18 the user reports
  five SIL resistor networks ordered and awaiting delivery. ACT inputs have
  TTL thresholds but must not float. Verify
  the voltage at a high-impedance FPGA pin is compatible with the 3.3 V bank.
  The external receiver/driver repository has not been modified in this task.
- [x] Correct the board wrapper's receiver/driver polarity. On 2026-10-18,
  receiver inputs and driver outputs are inverted at the physical boundary;
  driver inputs, including RUN drive, default high for inactive bus outputs.
  Simulation verifies idle, priority, flag and skip polarity.
- [ ] Verify those levels electrically after fitting the bias networks.
- [x] Initial target: HP 2100S, using the common HP 21xx I/O bus as the baseline.
  The user reports a shortest pulse of 200 ns and timing based on that interval:
  ten FPGA clocks at 50 MHz. Directed simulations cover four clock phases.
- [ ] Validate actual data setup/hold, response sampling, and external
  receiver/driver delays on the HP 2100S.
- [x] RUN intentionally has a receiver on P139 and driver on P138 connected
  to the same HP bus pin for model-dependent use. Drive remains inactive.
- [x] EDT is a computer/DCPC-to-interface input. The workbook and wrapper
  now treat P123 as an input; the core currently ignores it. Assigned unused
  receiver B5RI1: HP bus pin 62 → B5RI1 → FPGA P123. A4DO5 is now spare.
- [ ] Update the installed controller image before HP bus connection:
  the previously flashed image predates the EDT and polarity corrections and
  has FSMC disabled. Builds do not reprogram flash. Both programming dongles
  are currently disconnected; the user explicitly deferred programming.

## Q-04: Future STM32 interface wiring and timing

Status: FSMC wire-wrapped on 2026-10-18; firmware transport test added,
hardware programming and read/write verification pending.

- [x] Carrier identified as DevEBox STM32F4XX-M / STM32F407VET6, 8 MHz HSE;
  USB directly on PA11/PA12. ST-Link will program via SWD.
- [x] User reports the FSMC wiring is complete. The carrier top now enables
  all 19 wired signals using the STM32 workbook's FPGA pin assignments.
- [x] Add an isolated 16-bit scratch register at AD address 0xE (CPU address
  0x6000001C), plus a Make/CMake STM32duino USB CDC pattern-test program.
- [x] Compile STM32 firmware with the existing native ARM64 GNU Arm toolchain;
  ELF/BIN/HEX generated. FPGA synthesis, mapping, routing, 50 MHz timing and
  bitstream generation passed. All 14 controller simulation variants, the
  physical-wrapper simulation and 16 Python validation checks pass.

- [x] PB7/P75 is NADV, officially named `FSMC_NL`; the workbook is corrected.
- [x] Defer General Interrupt (PB9/P74) and DMA request (PB8/P67). Reserve
  their pins; plan register polling for initial firmware. The reference
  testbench does use `stm32_irq`, so polling will be an intentional change.
- [x] No external NE pin is required with the FPGA as the only FSMC device.
  Tie the enabled backend's internal NE low; keep NADV, NOE, and NWE idle high,
  including while the STM32 resets. Four-phase simulations also pass with NE
  permanently active. The current carrier top enables FSMC and holds NE low.
- [x] Define conservative initial STM32 FSMC timing at 168 MHz; see
  [firmware bring-up](../firmware/stm32/README.md).
- [ ] Connect programmers later, load matching images, and verify repeated
  USB-reported FSMC tests and physical timing. Neither device has been
  programmed in this milestone; full STM32 disk firmware remains deferred.

## Q-05: Controller-image cold boot

Status: resolved by the user's power-cycle confirmation on 2026-10-17.

- [x] Power-cycle the standalone carrier and confirm the new 2 Hz heartbeat
  resumes on P143 without a download command.

The located FPGA-only controller image is programmed and verified twice in SPI
flash, with the STM32 backend disabled. The previous flash contents (working
blink image) were backed up in full and verified before writing. Reconfiguration
was requested successfully. The user confirmed the faster heartbeat after
power cycling. This check confirms controller-image configuration
and clock activity, not HP bus operation or disk functionality. The driver
input-bias correction and actual HP interface testing remain outstanding.
