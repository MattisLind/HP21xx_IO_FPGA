# HP 21xx I/O board requirements

Initial requirements baseline: 2026-10-16.

For current bring-up state and continuation on another computer, read the
[Codex handover](../HANDOVER.md), updated 2026-10-25. It distinguishes installed
firmware from offline fixes and lists migration files and next diagnostic steps.

Build an HP 21xx I/O board that implements an HP 13210 disk interface using
an FPGA for the bus-facing logic and an STM32 for higher-level disk operations
backed by an SD card. The first milestone is to build, download, and run a
simple LED blink design on the FPGA.

## Reference material

| Source | Purpose |
| --- | --- |
| [HP 21xx IO bus.xlsx](HP%2021xx%20IO%20bus.xlsx) | HP bus signals, directions, and FPGA pin mapping. |
| [STM32F407VET.xlsx](STM32F407VET.xlsx) | STM32-to-FPGA pin mapping, including the FSMC bus. |
| [13210-90003 hardware manual](13210-90003_13210A_Disc_Drive_Interface_Kit_May78.pdf) | Original interface theory and schematics; figure 5-2 contains selection, flags and SKF. |
| [hp13210a.sv](../hp2116_verilog/hp13210a.sv) | Reference implementation of the FPGA-side HP 13210 interface. |
| [tb_hp2116.sv](../hp2116_verilog/tb_hp2116.sv) | Behavioral reference for the STM32/FSMC master and higher-level HP 7900 disk operations. |
| [Toolchain discussion](https://chatgpt.com/share/6ad24098-4704-83ed-a163-827fe3981cd2) | Proposed Docker/ISE build and native macOS programming workflow. |

The HDL reference baseline is submodule commit `f07b963`. The spreadsheets
define the intended wiring; unresolved entries must be clarified before
generating constraints for the affected signals.

The initial HP 2100S diagnostic was mistakenly configured for data **15** /
command **16**. On 2026-10-24 the user corrected this to **data 14 / command 15**,
both octal. DSN 151302 then reported `E50 UNIT 0 MISSING-PRESENT NONE`, consistent
with all drives starting not ready and no STM32 disk backend yet. The earlier
E3 on channel 16 does not establish a command-selection fault. Physical HP bus
operation is not fully accepted yet. See the [diagnostic analysis and standalone flag tests](../diagnostics/hp13210/README.md).

## Hardware and timing

- **HW-01:** The board shall use a Xilinx Spartan-6 XC6SLX9 in a 144-pin
  package and an STM32F407VET. Each device resides on a small carrier board
  containing its oscillator and other auxiliary components.
- **HW-02:** The FPGA design shall use the board's 50 MHz clock, with a
  corresponding 20 ns clock-period constraint. The reference testbench's
  current 100 MHz clock is not the target board clock.
- **HW-03:** FPGA pin constraints shall follow the two spreadsheets and the
  confirmed carrier-board connections. Constraints shall specify the actual
  package pins and I/O standards appropriate to the board's bank voltages.
- **HW-03a:** The initial host shall be an HP 2100S, with the common HP 21xx
  I/O bus as the baseline and model-dependent functions handled explicitly.
  Use the user-reported 200 ns shortest pulse (ten 50 MHz clocks) for initial
  verification. Validate data setup/hold and response delays on hardware.
- **HW-04:** External HP bus and STM32 signals shall be reviewed for clock-domain
  crossings. Asynchronous single-bit controls shall use suitable synchronization
  where needed; two-stage flip-flop synchronizers are an initial candidate.
  Multi-bit data shall be captured coherently using the bus protocol and its
  timing. Synchronizer latency shall be checked against bus response timing.
- **HW-05:** The carrier's Winbond W25Q16JV configuration flash shall use
  single-bit SPI initially: FPGA P38 to flash pin 1 (`/CS`), P70 to pin 6
  (`CLK`), P65 to pin 2 (`DO/IO1`, FPGA input), and P64 to pin 5 (`DI/IO0`,
  FPGA output). Flash pins 3/7 are reported NC; FPGA P60 (M1) has a pull-down
  and P69 (M0) a pull-up, selecting Master Serial/SPI. Verify flash pin 8 supply,
  pin 4 ground, and actual flash status before accepting persistent boot.
- **HW-06:** The carrier button is connected to FPGA P59. Its polarity and
  external bias remain to be established. Any use in synchronous logic shall
  include synchronization and, for button events, debouncing. P59 is user I/O;
  it is not the configuration-reset input `PROGRAM_B` (P37).

## Disk-interface architecture

- **IF-01:** The FPGA shall implement the lower-level HP 13210 bus interface,
  including selection, control/flag handling, interrupt/service signaling,
  and data/register transfers, using the reference HDL as the starting point.
- **IF-02:** The STM32 shall implement the higher-level disk behavior modeled
  in the top-level reference testbench, including command handling, read/write
  operations, seek/address handling, and disk status/attention reporting.
  Disk-image storage shall be backed by an SD card.
- **IF-03:** FPGA-to-STM32 communication shall use the spreadsheet's 16-bit
  FSMC connection. The reference uses multiplexed address/data phases, read
  and write strobes, and interrupt/data-request signals. Its register map
  shall be the initial basis for the hardware/firmware interface; any changes
  shall be documented consistently on both sides.
- **IF-03a:** PB7/P75 shall carry `FSMC_NL` (NADV, active-low address valid).
  General Interrupt and DMA request connections shall be deferred, with
  P74/P67 reserved. Initial firmware shall poll controller registers. With
  only one FSMC device, the enabled FPGA backend may hold its internal NE
  active without a physical NE connection. NADV, NOE, and NWE shall idle high,
  including during STM32 reset. The backend-disabled build remains inactive.
- **IF-04:** The `hp2116_verilog` submodule shall remain reference material.
  Required modules shall be copied into this repository's implementation
  sources and adapted for ISE 14.7 synthesis and the physical board.
  Simulation-only disk-image and STM32 model code shall inform the firmware
  behavior rather than become FPGA implementation logic.
- **IF-05:** The next milestone shall port the reference HP13210 controller
  into local Verilog-2001 sources for ISE 14.7 at 50 MHz. First validate HP
  flags, control, skip, priority/interrupt, and register/data handling with no
  STM32 firmware. Keep the backend interface and register map for later work.
  The user reports the reference passes disk diagnostics and boots RTE II in
  Verilator; repeat that full-system validation separately after porting.
- **IF-06:** Without the backend, the FPGA shall not fabricate disk data or
  completion. Drives shall start not-ready, the FSMC bus shall remain released,
  and backend IRQs shall remain disabled. A mock backend may be used in FPGA
  simulations without adding STM32 firmware to this phase.

The initial local implementation and its verification scope are described in
the [FPGA port guide](../fpga/hp13210/README.md).
On 2026-10-17 the local port passed 50 MHz simulations with the backend disabled
and with a mock backend, followed by full ISE implementation and no-bitfile DRC.
TRACE reports zero timing errors. A subsequent located, FPGA-only carrier
image with the backend disabled and a 2 Hz heartbeat was built, programmed into
SPI flash, verified twice, and reloaded on 2026-10-17. The previous blink image
was backed up first. The user confirmed the 2 Hz heartbeat after power cycling,
resolving Q-05. Physical HP bus validation remains pending.

On 2026-10-18, the user reported the FSMC interface wire-wrapped and five
4.7 kΩ SIL pull-up networks ordered for the driver inputs. The current FPGA
sources enable the 19 FSMC pins, add a 16-bit transport scratchpad at AD `0xE`
(STM32 CPU address `0x6000001C`), and correct physical HP receiver/driver
inversion. Both programming dongles are disconnected; programming is explicitly
deferred at that time. On 2026-10-23, the user confirmed the latest image works
in SRAM, then it was programmed into SPI flash and verified twice following a
verified full-flash backup. The user then confirmed the new LED pattern after
power cycling on 2026-10-23; persistent boot of this revision is accepted.

- **IF-07:** Provide an isolated full-width read/write scratchpad for FSMC
  bring-up. Tests shall cover fixed patterns, walking bits, retention, and
  bus release without changing disk-controller state.
- **TC-STM32-01:** Build DevEBox STM32F4XX-M / STM32F407VET6 test firmware
  using command-line GNU Arm GCC and STM32duino with CMake-generated Makefiles.
  Use its 8 MHz HSE for a 168 MHz CPU and 48 MHz USB clock. Provide USB CDC
  pattern-test reports and later ST-Link/SWD programming as separate targets.
  The firmware shall wait for an operator command before accessing FSMC.
  High-level disk firmware and SD-card integration remain later milestones.

See [STM32 build and test instructions](../firmware/stm32/README.md).

- **FW-DISK-01 (2026-10-24):** Implement a separate STM32 disk-backend image
  following the reference testbench's register protocol and command behavior.
  Retain the existing USB/FSMC transport test and its build/program targets;
  physical transport testing must precede loading the disk backend. No devices
  are connected or to be accessed during this implementation task.
- **FW-DISK-02:** Use the carrier's SDIO socket with FAT storage. Load drive
  assignments for units 0–3 from a simple root configuration file and open
  existing disk images under `/images`. Missing or invalid images remain
  offline. Keep geometry and little-endian word layout compatible with the
  testbench's raw images.
- **FW-DISK-03:** Start with basic reads/writes, seek/address handling, ready
  status and completion handshakes. Buffer transfers to avoid filesystem
  calls during per-word FSMC service. Defer write protection and the
  diagnostic's precisely timed DMA-overrun case; prioritize basic operation.

The implementation, example configuration, dependency versions and current
validation limits are in the [STM32 disk-backend guide](../firmware/stm32-disk/README.md).

- **HW-LED-01 (2026-10-19):** Either assigned HP select code shall trigger a
  100 ms pulse on P143. A new selection during a pulse shall share that pulse
  without extending it. With no selection activity, generate the same 100 ms
  pulse every two seconds; every selection restarts the idle interval,
  including selections during an existing LED pulse.
  A continuously held selection shall trigger once and suppress the idle
  heartbeat until released. Both select channels shall be synchronized and
  detected independently. Programming remains deferred while dongles are
  disconnected.

## Toolchain

Implementation instructions, commands, and current test results are in the
[toolchain guide](../toolchain/README.md).

Bring-up checkpoint, 2026-10-16: `hp21xx-ise:14.7` is built from the supplied
vendor archive. Synthesis, mapping, routing, TRACE, and BitGen's no-bitfile DRC
have passed for the provisional XC6SLX9 target at 50 MHz. Cable firmware loading
has also passed. The connected FPGA is detected through the DLC9G clone as
XC6SLX9 revision C, IDCODE `0x24001093`. A hardware blink bitstream has now been
built for `xc6slx9-2-tqg144`, clock P56, LED P143, and LVCMOS33. Timing at 50 MHz
and BitGen DRC passed, and the SRAM download completed successfully. The
user confirmed that the LED blinks. The first hardware blink milestone is
complete; the build, SRAM download, and visible blink are verified.

- **TC-01:** FPGA synthesis, implementation, and bitstream generation shall
  run using Xilinx ISE 14.7 inside a Docker container.
- **TC-02:** The build shall be repeatable from documented command-line
  commands or a Makefile. Record the image version or digest, ISE setup,
  selected FPGA part, source files, constraints, and build commands. Preserve
  build logs, timing reports, and the generated `.bit` file on the host.
- **TC-03:** Start from the approach in the linked discussion: a Linux
  `amd64` ISE container, with native macOS JTAG programming as the proposed
  download path. The discussion considers `vmunoz82/ise14`, a possible one-time
  image build on x86-64 Linux, and `openFPGALoader` on the M2 Mac. The image
  shall be tested on the M2 Mac. The implemented provisioning path reads the
  supplied VM's disk directly and packages the Spartan-6 CLI subset locally.
- **TC-04:** Container execution shall explicitly select `linux/amd64`.
  Verify x86-64 executable operation and bidirectional project-file access
  on the Apple Silicon host before testing ISE.
- **TC-05:** The runtime image and the licensed ISE installation shall be
  provisioned separately. Support a read-only mount of an installed Linux
  `ISE_DS` directory, or an existing image containing ISE and Python 3.8+.
  Record the actual image ID/digest used for each implementation build.
- **TC-06:** Source ISE's `settings64.sh` before running the tools. Check
  availability of XST, NGDBuild, MAP, PAR, TRACE, and BitGen. A help/version
  check alone shall not count as a working synthesis toolchain.
- **TC-07:** Provide separate commands for host diagnostics, runtime testing,
  HDL simulation, implementation smoke testing, hardware bitstream generation,
  JTAG detection, and volatile FPGA programming.
- **TC-08:** The implementation flow shall run XST, NGDBuild, MAP, PAR,
  TRACE, and then BitGen. Stop on any failed step. Before BitGen, require
  analyzed paths under the 20 ns clock constraint and a passing timing summary.
- **TC-09:** The smoke test may use a provisional part and automatic pin
  placement to exercise synthesis, implementation, and timing analysis. It
  shall not generate a bitstream for downloading. Hardware builds require
  the actual FPGA part, clock and LED pins, polarity, and I/O standard.
- **TC-10:** Save stage logs, generated project/constraint files, timing
  reports, input fingerprints, image identity, and successful-build evidence
  under `build/`. Programming shall reject a stale or modified bitstream.
- **TC-11:** JTAG programming shall run on the host using a cable driver
  supported by the installed programmer. Validate the exact cable and target
  together; do not assume a Xilinx-compatible cable works on macOS. Initial
  programming shall use volatile FPGA SRAM.
  The available cable is a Xilinx Platform Cable USB DLC9G clone. Evaluate
  native `xc3sprog` with its `xpc` backend; verify the clone's USB identity
  and any required volatile cable firmware before declaring it supported.
  The clone's cold state is `03fd:000d`, which the referenced ISE driver rules
  map to `xusb_emb.hex`. Native RAM loading has been verified to change it to
  `03fd:0008`. Target-chain detection has passed with the connected FPGA:
  XC6SLX9 revision C, IDCODE `0x24001093`, at JTAG position 0.
- **TC-12:** Keep vendor installers, licenses, local board settings, and
  generated build outputs out of Git. Toolchain setup shall not require
  changes inside the reference HDL submodule.
- **TC-13:** Persistent configuration shall program and verify the W25Q16JV
  through a temporary FPGA JTAG-to-SPI bridge compatible with native
  `xc3sprog` and the DLC9G. Identify the flash and save a complete backup before
  erase/program operations. The initial boot image shall use SPI x1 and CCLK
  startup, starting at flash address zero. Verify independent boot after power
  cycling. See the [flash bring-up guide](../toolchain/FLASH.md).

## First milestone: FPGA LED blink

- **BL-01:** Create a minimal, self-contained FPGA design that derives a
  visible, documented LED blink rate from the 50 MHz board clock. It shall
  have a defined initial state and require no STM32 firmware, SD card, or
  HP bus transactions. The initial implementation shall blink at 1 Hz, with
  0.5 seconds on and 0.5 seconds off.
- **BL-02:** Confirm the complete FPGA part designation, clock pin, LED pin,
  LED polarity, and relevant I/O voltage before assigning the blink design's
  pins. Other connected signals shall have documented inactive or
  high-impedance behavior appropriate to the board.
- **BL-03:** Build the design through synthesis, mapping, place and route,
  and bitstream generation using the Docker/ISE flow. The design shall meet
  the 20 ns clock constraint, with no unresolved implementation errors.
- **BL-04:** Document the programmer, cable selection, and download command.
  Detect the target FPGA, download the generated bitstream, and observe the
  expected LED blink on the physical carrier board.

The milestone is accepted when the documented build and download procedure
can be repeated and produces the expected blink. Keep the build/timing logs,
programmer output, and a record of the observed blink rate. A generated
bitstream alone does not demonstrate hardware success. Persistent boot from
configuration flash is a follow-up unless included explicitly in bring-up.

## Details to resolve during implementation

Hardware questions are tracked in the
[outstanding questions list](OUTSTANDING_QUESTIONS.md). Q-01 was resolved on
2026-10-17: flash pins 3/7 are NC, M1 (P60) is pulled down, and M0 (P69) is
pulled up.

- Exact carrier-board models and startup/reset behavior. The reported FPGA
  markings identify XC6SLX9, TQG144, speed grade -2, commercial temperature
  range (`2C`); use ISE part `xc6slx9-2-tqg144`.
  The user confirms the 50 MHz clock on package P56
  and 3.3 V LVCMOS I/O (`LVCMOS33`). The observed blink confirms the LED on P143;
  its electrical polarity has not been established by this blink test.
  P57 is now assigned to HP IOB4 output and P58 to HP IOB12 output. Use P143
  for the LED; P57 is no longer an LED fallback.
- Persistent boot: W25Q16JV identity `EF 40 15` and QE=1 are verified. The
  carrier-specific JTAG-to-SPI bridge passed implementation and actual flash
  access. The original full 2 MiB flash was backed up and verified, then the
  blink boot image was written and verified twice. A reload command was sent.
  The user confirmed blinking after a power cycle without a download on
  2026-10-17. Q-02 is resolved and the persistent blink milestone is complete.
- HP bus spreadsheet updated on 2026-10-17: output `IOB4` at connector pin 42
  now uses P57; output `IOB12` at connector pin 57 moves from flash CCLK P70
  to P58. The STM32 sheet reserves those pins for the HP outputs. `RUN`
  intentionally uses P139 for receive and P138 for drive on the same bus pin;
  drive remains inactive initially. EDT is corrected to an input on P123,
  matching the computer/DCPC-to-interface direction. HP bus pin 62 connects
  through receiver B5RI1 to FPGA P123; the former A4DO5 driver is spare.
  The SPI flash image was updated on 2026-10-23 and includes this correction.
  Variant-specific
  `IOB16/BIOS` and `SFSB/BIOI` behavior also needs clarification.
- STM32 spreadsheet: corrected `FSMC_NL`/NADV naming; interrupt and DMA request
  are deferred. No external NE connection is planned for the single device.
  Unlike the interrupt-driven reference testbench, initial firmware will poll.
- Physical HP bus polarity and timing, FSMC timing, and the synchronization
  strategy needed to preserve both interfaces' behavior at 50 MHz.
  Receiver and driver inversion is confirmed; the external schematic's
  5 V pull-ups at driver DI inputs were a user-confirmed design error and have
  been removed. Five 4.7 kΩ SIL networks are on order to provide 3.3 V pull-ups;
  fitting and electrical verification remain pending before HP connection.
- SD-card connection and storage format, followed by the detailed firmware
  scope and acceptance tests for the complete disk interface.
