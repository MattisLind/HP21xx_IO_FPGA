# Carrier SPI flash bring-up

The user reports a Winbond `25Q16JVSIQ` device. The W25Q16JV has 16 Mbit
(2 MiB) capacity, sufficient for the current XC6SLX9 blink image. Confirm the
full ordering code and actual JEDEC ID; `EF 40 15` is expected for the IQ variant.

## Reported connections

| FPGA package pin | FPGA configuration function | Winbond pin | SPI function |
| --- | --- | --- | --- |
| P38 | CSO_B | 1 | /CS, active-low chip select |
| P70 | CCLK | 6 | CLK, clock into flash |
| P65 | DIN / MISO | 2 | DO / IO1, flash output into FPGA |
| P64 | MOSI | 5 | DI / IO0, FPGA output into flash |

These match the Spartan-6 dedicated single-bit SPI configuration connections.
The reported wiring has been exercised successfully by flash identification,
full backup, programming, readback verification, and autonomous boot.
The 50 MHz application clock on P56 is separate from configuration CCLK on P70.

## Remaining hardware checks

On 2026-10-17, the user reported flash pins 3 and 7 unconnected, FPGA P60
pulled down, and P69 pulled up. This resolves
[question Q-01](../requirements/OUTSTANDING_QUESTIONS.md#q-01-spi-flash-auxiliary-pins-and-boot-mode-straps).
The straps select Master Serial/SPI. The bridge has since been built and flash
identification, full backup, programming, and readback verification have passed.

- Flash pin 8 must have the proper supply (3.3 V is suitable), pin 4 must be
  ground, and the device needs local supply decoupling. Bank 2 is reported 3.3 V.
- Pin 3 (IO2 / /WP) and pin 7 (IO3 / /HOLD) are both reported NC. Their function
  depends on the flash's QE setting. IQ parts default to QE=1, disabling /WP
  and /HOLD. If QE=0, these active-low controls need defined inactive levels
  for normal operation. Read the actual QE setting and preserve QE=1 with
  these pins unconnected. Quad wiring is unnecessary for initial x1 SPI.
- For autonomous Master Serial/SPI boot, M1 on P60 must be low and M0 on P69
  high when configuration mode is sampled. The reported pull-down on P60 and
  pull-up on P69 match this requirement.
  Successful JTAG programming alone does not establish these settings.
- Confirm the configuration circuit around PROGRAM_B (P37), INIT_B (P39),
  and DONE (P71), including its pull-ups, against UG380. The existing successful
  JTAG blink validates part of this circuit, but does not prove SPI boot.
- The button on P59 is ordinary user I/O (`IO_L13N_D10_2`), not PROGRAM_B.
  Determine its idle/pressed levels and bias before using it. It cannot directly
  reload the flash configuration without suitable FPGA logic.

## Programming method

The repository now provides these commands:

```sh
make programmer-build   # Includes read-only Winbond status reporting.
make spi-bridge         # ISE build plus a separate CCLK/SPI-x1 blink boot image.
make flash-probe        # Loads the bridge; reads JEDEC ID and SR1/SR2/SR3.
make flash-backup       # Saves and verifies exactly 2 MiB, refusing overwrite.
make flash-program      # Requires the verified backup, writes and verifies blink.
```

`flash-program` checks that the original backup still matches the attached flash
before writing, then requests FPGA reconfiguration from flash. After successful
programming, repeat the power-cycle test without downloading an SRAM image.
The probe/backup steps replace the running blink with the temporary bridge.
The wrapper accepts only JEDEC `EF 40 15` and requires QE=1, no active erase/write,
and no array-protection settings. It does not modify flash status registers.

Build evidence and bitstream hashes are stored in `build/spi/success.json`.
The original backup is `build/spi/original.bin`, with verification evidence in
`build/spi/backup.json`. Programming evidence goes to `build/spi/programmed.json`.
Keep these files when rebuilding; the backup is never automatically replaced.
This initial programming command requires the flash still to match the original
backup. After a successful write it deliberately refuses to overwrite changed
contents on another invocation; a future update/restore workflow must account
for the current contents explicitly.

Use the existing native ARM64 xc3sprog and DLC9G with indirect SPI programming:

1. Build a temporary BSCAN/USER1-to-SPI bridge for `xc6slx9-2-tqg144` and the
   four connections above. The pinned xc3sprog source already contains
   `bscan_spi/bscan_s6_spi_isf_ext.v` and its included `bscan_common.v` under
   `build/tools/xc3sprog-src/`. Adapt its constraints for this carrier; the
   bundled CSG324/FG484 bitstreams are not suitable for TQG144.
2. Load that bridge into FPGA SRAM over JTAG. It replaces the running blink
   until another image is loaded or the device reconfigures.
3. Read JEDEC identity and flash status, then back up all 2,097,152 bytes.
   The installed programmer's Winbond handler accepts type 0x40, density 0x15,
   with 256-byte pages and 4 KiB sectors. These operations have been tested on
   this carrier. Different flash-protection settings may require extra handling.
4. Generate the blink boot image with BitGen `StartupClk:Cclk`,
   `spi_buswidth:1`, and an initial `ConfigRate:2`. These options are present
   in the installed ISE 14.7 Spartan-6 `bitgen.usg`. Program at address zero
   with explicit file format and verify readback. Retain the original backup.
5. Power cycle the carrier and confirm the LED blinks without a JTAG download.

The bridge's UCF uses these pin constraints (matching its upstream port names):

```ucf
NET "CSB"   LOC = "P38" | IOSTANDARD = LVCMOS33 | DRIVE = 8 | SLEW = SLOW;
NET "DRCK1" LOC = "P70" | IOSTANDARD = LVCMOS33 | DRIVE = 8 | SLEW = SLOW;
NET "MISO"  LOC = "P65" | IOSTANDARD = LVCMOS33;
NET "MOSI"  LOC = "P64" | IOSTANDARD = LVCMOS33 | DRIVE = 8 | SLEW = SLOW;
```

The build also constrains the internal BSCAN clock net `DRCK1_OBUF` with a
100 ns period. Applying that constraint to the external `DRCK1` output pad
instead covers zero paths; the build rejects that result. The first attempt
demonstrating this is retained under `build/spi-clock-pad-attempt/`.

After building and validating a carrier-specific `bridge.bit`, xc3sprog uses
an attached `-I` filename (no separating space) to load the bridge and enter
indirect SPI mode. The equivalent identification and backup commands tested on
this carrier are:

```sh
build/tools/xc3sprog-build/xc3sprog -c xpc -Ibuild/spi/bridge.bit
build/tools/xc3sprog-build/xc3sprog -c xpc -I build/spi/original.bin:r:0:BIN:2097152
```

The second command uses bare `-I` because the bridge is already loaded.
The `r` action refuses to overwrite an existing backup. Explicit length prevents
the programmer from trimming trailing erased bytes. The programmer's BIN
format has its own bit-order convention; use the same format when restoring.
Do not substitute a raw file for a `.bit` or `.mcs` file without selecting the
correct format. For Xilinx-generated MCS, upstream help specifies `IHEX`.

## Verified results, 2026-10-17

- Bridge synthesis, mapping, routing, and TRACE passed. The internal clock
  constraint covers 1,647 paths, with zero timing errors, minimum period
  9.198 ns, setup slack 45.401 ns, and hold slack 0.334 ns at the 100 ns bound.
- Upstream bridge HDL produces seven synthesis warnings (unused signals and
  width truncations) and one gated-clock DRC warning for its reset logic.
  BitGen produced the bridge successfully; the blink boot image DRC had zero
  errors and zero warnings.
- Actual flash identity is `EF 40 15`, unique number `006786091cea026d`,
  capacity 2,097,152 bytes. Status is SR1=`00`, SR2=`02`, SR3=`60`: QE set,
  no busy operation, and no active array protection.
- The original full-flash backup was verified against the device. It contained
  only erased `FF` bytes. Backup SHA-256:
  `4bda3a28f4ffe603c0ec1258c0034d65a1a0d35ab7bd523a834608adabf03cc5`.
- The CCLK/SPI-x1 blink boot image was programmed at address zero. The
  programmer's automatic verify and a second independent verify both passed.
  QE and protection status remained unchanged.
- `xc3sprog -c xpc -R` completed, requesting FPGA reconfiguration from flash.
  The user confirmed the LED blinks after this reload, then powered the carrier
  off and back on and confirmed the LED resumed blinking without a download.
  Automatic SPI-flash boot is verified; this completes
  [Q-02](../requirements/OUTSTANDING_QUESTIONS.md#q-02-confirm-automatic-blink-after-power-cycling).
- Blink simulation and all 14 validation tests passed, including rejection of
  unexpected flash identity, disabled QE, missing status, and protected flash.

## Updating the controller

For subsequent controller images, use `make controller-build` followed by
`make controller-program`. That workflow saves and verifies a fresh backup of
the current flash before each update, preserving the original backups and the
working blink image. See the [controller guide](../fpga/hp13210/README.md#located-fpga-only-carrier-image).

On 2026-10-17 this update workflow programmed and verified the located FPGA-only
HP13210 carrier image. The preceding blink flash contents were backed up and
verified first; the original erased-flash backup is also preserved. Both image
readback checks passed and FPGA reload was requested. The controller has a
2 Hz heartbeat, which the user confirmed after power cycling. Q-05 is resolved.

## Sources

- [AMD UG385: Spartan-6 packaging and pinouts](https://docs.amd.com/v/u/en-US/ug385), TQG144 table.
- [AMD UG380: Spartan-6 configuration](https://docs.amd.com/v/u/en-US/ug380), Master Serial/SPI configuration and mode pins.
- [Winbond W25Q16JV datasheet, manufacturer document mirrored on device.report](https://device.report/m/97430b7ae9fc375867bdbc6ad4782c48e21d15bbe12cb3293ae0b331e3ad1a5c), pinout, QE, and JEDEC identification.
- [Pinned xc3sprog source](https://github.com/UweBonnes/xc3sprog/tree/2bba5381d64b98bca40cb83c9d1d56aaceb4c12f), `bscan_spi/`, `xc3sprog.cpp`, and `progalgspiflash.cpp`.
