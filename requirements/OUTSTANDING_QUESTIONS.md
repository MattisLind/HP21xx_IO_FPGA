# Outstanding questions

## Q-07: STM32 FAT disk backend

Status: disk backend programmed and verified through ST-Link on 2026-10-25,
after the user's successful USB/FSMC test. After preparing the card, the user's
USB screenshot confirms FAT mounted and drives 0–3 READY. It also shows
`commands=136 errors=136 trace_dropped=0` with the HP connected but idle.
The subsequent diagnostic reaches section 1 step 2 (seek cylinder 0) and reports
E21, missing/wrong-unit attention. USB now shows `??`, `E04` and `CM` for drives
3 and 0. Storage initialization passes; command capture and attention behavior
still require investigation before disk-operation acceptance.
After leaving custom-test entry, a further run stops earlier at initial status:
HP E64, status `000003` versus expected zero (data error plus aggregate error).
The installed unsupported-command handler can set this data-error bit; its
offline correction remains undownloaded. Details are in the diagnostic guide.

- [x] Add a separate `firmware/stm32-disk` image, keeping the transport test's
  sources, ELF and successful-build receipt unchanged during this task.
- [x] Read `/hp13210.cfg` on FAT and map drive0–drive3 to existing images under
  `/images`; valid images are writable, missing/invalid images stay offline.
- [x] Port basic read/write, partial-sector filling, asynchronous seek,
  check-data, status and attention handshakes. Poll CSR, preserving command
  requests acknowledged by reads; IRQ/DRQ wires are not required.
- [x] Use pinned STM32SD/FatFs dependencies and compile for the F407 carrier.
- [x] Host-test the actual C++ protocol engine with sanitizers and mock media.
- [x] Add short USB operation/result codes and E01–E16 errors, plus a bounded
  nonblocking event queue and E99/drop accounting. USB drains only while idle;
  firmware build and host tests cover runtime traces. The user's diagnostic
  screenshot confirms short trace output. Code meanings are in the backend guide.
- [x] Run the old USB/FSMC transport test and verify repeated passes. The user's
  photo on 2026-10-25 shows PASS 1 through PASS 19, each with 294 patterns,
  588 reads and zero failed passes: 5,586 writes and 11,172 reads in total.
- [x] Save and verify the previous 512 KiB STM32 flash image, then program,
  verify and reset into the disk backend, including short USB trace codes.
  Evidence: `build/stm32-disk/programmed.json`, timestamped programming logs
  and the backup under `build/stm32-disk/backups/`.
- [x] Compare FPGA SPI flash against the current validated bitstream on
  2026-10-25. Verification passed for SHA-256
  `3f8b76e5db2ea251ce3645cf7540c7ddaf0d7c71052fc543d5a6a788211e0fe6`.
  No flash rewrite was needed. The temporary SPI bridge was replaced by
  reloading the existing flash image. Receipt: `build/controller-board/flash-verified.json`.
- [x] Verify SD mounting and configuration on the STM32: the user's screenshot
  reports FAT mounted and all four configured images READY.
- [x] Identify visible runtime errors: STM32 E04 denotes unsupported commands.
  Correct their handling to match the reference daemon: log and ignore, without
  creating HP attention/completion. Add retained raw FSMC observations to `?`.
  The correction is tested offline and has not been downloaded.
- [ ] Determine why unsupported commands arrive and whether counters increase
  while the HP is idle; resolve diagnostic E21 on seek. Programmers are currently
  disconnected. USB trace drains only while idle and can be delayed. The current
  counters do not prove successful disk commands. See the diagnostic guide for
  the source-derived attention check and limits of the available evidence.
- [ ] Compare real-machine reads/writes against a disposable image's host bytes.

SD preparation update, 2026-10-25: the user's 8 GB `7900EMU` card is mounted
as MBR/FAT32 on macOS and its latest read-only filesystem check passed. The
proposed reformat never ran. The four user-supplied `drive0.img`–`drive3.img`
files have been moved into `/images`, with `/hp13210.cfg` assigning them to
drives 0–3. Each image is exactly 4,988,928 bytes, and SHA-256 hashes matched
before/after moving. Receipt: `build/sd-card-inspection/7900EMU-prepared.json`.
The subsequent USB screenshot confirms the prepared card mounts on the STM32
and all four images open successfully. This verifies initialization, not the
contents of sector transfers.
- [ ] Validate read startup latency, data throughput and write completion on
  hardware, then rerun HP diagnostics and test RTE II boot.
- [ ] Add write protection and cylinder metadata later. The accurately timed
  DMA-overrun diagnostic remains deferred by user request.

See [backend build, configuration and limitations](../firmware/stm32-disk/README.md).

## Q-06: HP 2100S diagnostic bring-up

Status: corrected diagnostic select codes on 2026-10-24; E50 drive-not-ready
result matches the missing disk backend. Analysis remains offline; no downloads.

- [x] Identify diagnostic: DSN 151302, with original sources in the user's
  Type 4 archive. E3 means SFC did not skip after CLF.
- [x] Correct select codes: **data 14 / command 15**, octal. The earlier
  diagnostic setting 15/16 was mistaken, so E3 on 16 does not establish an
  actual command-channel fault.
- [x] Clarify LED observation: idle heartbeat worked, selection response was
  not observed. Configuration/clock activity is present; selection remains
  unverified.
- [x] Locate the exact check and common error halt. M=012135/data=102001,
  P=012136 and A=3 match the diagnostic's E3 reporting path.
- [x] Add independent flag tests for 14/15, paired/isolation tests, a delayed
  variant and repeatable scope loops. Offline instruction-flow and tape-format
  checks are available; these are not hardware acceptance tests.
- [x] Inspect the supplied 13210-90003 hardware manual. Figure 5-2 confirms
  the connector pins and separate selection/flag/skip paths.
- [x] Trace retest `E50 UNIT 0 MISSING-PRESENT NONE`: status reports unit 0
  not ready and no ready alternatives among units 0–3. HLT 6 at 002557,
  P=002560 and A=0 match the first-pass E50 halt path. All four drives start
  not ready; STM32 firmware currently provides no disk backend.
- [x] Trace the normal path before E50. With no earlier errors/continued halts,
  both channels passed flag and STF selection-isolation checks, command channel
  15 passed HP interrupt/acknowledgement checks, and startup completed repeated
  status plus four two-word ADDRESS RECORD handshakes. The direct all-not-ready
  path makes 16 status requests in total. Disk-test sections and DMA transfers
  have not started; this is not full data-path or disk acceptance.
- [ ] Run the small tests on 14/15 and record each halt; verify physical
  read/write transport and timing before accepting full HP bus operation.
- [ ] Implement STM32 drive status and command servicing to bring a real
  emulated drive online; clearing not-ready alone is not a disk backend.
- [ ] Review POPIO behavior: hardware section 4-5 specifies setting both
  flags; the port sets the buffers and clears flags until ENF. This is a
  separate equivalence question, not an established explanation for E3.

See [failure analysis and test instructions](../diagnostics/hp13210/README.md).

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
- [x] Update the installed controller image: on 2026-10-23 the user confirmed
  the SRAM-loaded image works, then authorized SPI flash programming. The latest
  image includes EDT/polarity corrections, FSMC and the activity/idle LED.
  The previous 2 MiB image was backed up and verified; programming and a second
  verification passed, and reload from flash was requested.

## Q-04: Future STM32 interface wiring and timing

Status: FSMC wire-wrapped on 2026-10-18; both devices programmed and verified
on 2026-10-23. Physical scratch-register read/write testing passed on
2026-10-25; full register-map/protocol and timing-margin validation remain.

Update 2026-10-23: the latest validated FPGA image, including the FSMC
scratchpad, physical HP polarity fixes and 100 ms activity/two-second idle LED,
was successfully downloaded over JTAG into volatile SRAM. The FPGA was detected
as XC6SLX9 revision C, IDCODE 0x24001093. SPI flash was not modified; a power
cycle would still load the older flash image at that point. STM32 programming and physical
FSMC read/write testing remain pending. Download evidence is in
`build/controller-board/sram-downloaded.json` and `sram-download.log`.

Later on 2026-10-23, SPI flash was updated to this same working image and
verified twice. Flash status remains SR1/SR2/SR3 = 00/02/60. The latest receipt
is `build/controller-board/programmed.json`. STM32 programming and physical
FSMC testing remain pending.

- [x] The user confirmed on 2026-10-23 that the latest 100 ms / two-second idle
  LED pattern starts automatically after power cycling. Persistent boot of
  this newly programmed revision is accepted; physical HP/FSMC tests remain.

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
- [x] Program and verify the STM32 USB/FSMC test firmware via ST-Link/SWD.
- [x] The user confirmed the STM32 PA1 heartbeat blinks on 2026-10-23.
- [x] Verify repeated USB-reported FSMC scratch-register tests. On 2026-10-25
  the user's photo shows 19 consecutive passing iterations with no failures,
  at CPU address 0x6000001C / AD address 0x000E, HCLK=168 MHz.
- [ ] Measure physical timing margins and verify the full controller register
  map and disk protocol. The scratch test alone does not establish these.

Update 2026-10-23: FPGA programming and cold boot are accepted. Replacing the
suspected charge-only USB cable resolved ST-Link USB detection: 0483:3748,
firmware V2J37S7. OpenOCD now opens the probe, but cannot connect to the target
and initially reported target voltage 0 V. After the user reconnected/powered
the target, OpenOCD detected Cortex-M4, device ID 0x101f6413, 512 KiB flash,
and 3.39 V. Programming and verification succeeded and the target was reset
to run. The automatic PA1 heartbeat is 100 ms on every two seconds,
independently of USB/DTR. The user confirmed the LED blinks; FSMC
accesses still require the explicit `t` command and have not been run.
Evidence: `build/stm32/programmed.json` and `build/stm32-program.log`.

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
