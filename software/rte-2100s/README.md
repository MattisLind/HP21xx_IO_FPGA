# RTE for the 32K-word HP 2100S

This generates **HP 29016D RTE-MH (1971)** for the physical HP 2100S and the
STM32/FPGA 13210 disk emulator. The source is the Roberto Sancho / J. David
Bryan RTE restoration kit updated in January 2020, already available locally
in `~/Downloads/RTE`. Its original documentation identifies this as the first
RTE, predating RTE-II; the repository's old `RTE_MH.disc` comes from that kit.

The generation uses the 2100 CPU, 32K words, its standard EAU, memory protect,
and DMA. It uses software arithmetic libraries without optional FP or FFP
firmware. The console uses the 12531-compatible TTY driver.

An [ALGOL chess build](chess/README.md) compiles and links the original chess
sources under this RTE and produces a separate disk image with CHESS installed.

| Device | Select code (octal) |
| --- | --- |
| Time base generator | 10 |
| Serial console | 11 |
| Paper tape reader | 12 |
| Paper tape punch | 13 |
| 13210 disk data | 14 |
| 13210 disk command | 15 |

There is no printer driver, printer equipment-table entry, or printer interrupt
entry. Listing output goes to the console. The interrupt table is entered in
ascending select-code order, as RTGEN requires.

## Generate the image

From the repository root:

```sh
python3 scripts/rte2100s.py
```

The helper defaults to `~/Downloads/RTE` for the extracted restoration kit and
`hp2100` from PATH, falling back to `~/simh/BIN/hp2100`. Explicit paths are
also accepted:

```sh
python3 scripts/rte2100s.py \
  --source "$HOME/Downloads/RTE" \
  --simh "$HOME/simh/BIN/hp2100" \
  --output build/rte-2100s-new
```

The output directory must be new. The helper copies the input media, generates
the system from relocatable modules using SIMH, initializes both file-manager
areas, and runs the verification below. It does not alter the distribution,
the old Verilog disk image, or an SD card.

The SIMH scripts use the standard `EXPECT`/`SEND` commands. The generation
inherits the kit's SXL `TERMF` replacement; RTGEN reports `ERR 08` and `ERR 05`
for that replacement, exactly as in the distribution transcript. The helper
checks that these are the only RTGEN diagnostics and that no unresolved
externals remain.

Default outputs are under `build/rte-2100s/`:

| File | Purpose |
| --- | --- |
| `sd-card/images/rte-2100s.img` | Ready-to-copy disk image with the IOTST test program |
| `sd-card/hp13210.cfg` | Map the image to drive 0, leave drives 1–3 offline |
| `rte-2100s-boot.abs` | RTGEN's matching bootstrap paper tape, configured for SC 14/15 |
| `rte-2100s-panel.txt` | The same bootstrap as 53 octal words for front-panel entry |
| `boot.ini`, `hardware.ini` | Interactive SIMH configuration |
| `generate.log` | System-generation and initial filesystem transcript |
| `verify.log` | Assembly, linking, disk write/read, and execution transcript |
| `verify-reboot.log` | Second cold boot and execution from the saved file |
| `manifest.json` | Input, simulator, configuration and artifact SHA-256 hashes |

`rte-2100s.img` in the output root is identical to the SD-card copy.

## Copy to the disk emulator

Copy the contents of `build/rte-2100s/sd-card/` to a FAT16/FAT32 SD card:

```text
/hp13210.cfg
/images/rte-2100s.img
```

The configuration is:

```ini
drive0=rte-2100s.img
drive1=none
drive2=none
drive3=none
```

If the card already has a configuration, edit its drive mapping to match this
instead of replacing it blindly. Reset the STM32 after changing the card.

The image is exactly **4,988,928 bytes**, with no header or SIMH footer:
203 cylinders × 4 heads × 24 sectors × 128 little-endian 16-bit words.
This is the [STM32 backend's native layout](../../firmware/stm32-disk/README.md).
No byte swapping or format conversion is needed.

Only physical drive 0 is used. RTE logical unit 2 is the fixed platter
(subchannel 0, heads 2/3); LU 3 is the removable platter (subchannel 1,
heads 0/1). Both platters are in the **same image**. Each has 203 logical
tracks of 48 × 128-word sectors. FMGR reports these as 96 × 64-word sectors.
The SYS file area starts at logical track 100 decimal, leaving the system
tracks reserved; AUX starts at track 0.

### Additional attached drives

On 2026-10-31, SIMH tests using copies of the actual `7900EMU` card images
passed with drive 0 alone, with all four configured drives attached (1–3
zero-filled), and with the old diagnostic image substituted for drive 1.
Each case booted, listed FMGR, played two chess moves, and ran IOTST.
The command traces were identical: 267 disk command words, all for physical
drive 0. The extra images were never accessed and remained unchanged.

This generated system maps only the two platters of drive 0; attaching extra
drives does not add RTE logical units. The result applies to this HP 29016D
RTE build. A separate RTE-II system or a configuration that uses additional
drives was not tested. See the [test report and transcripts](../../build/rte-2100s-multidisk-20261031/README.md).

## Boot on the HP 2100S

Use **the generated RTE bootstrap**. SIMH's standard `BOOT DPC`/BMDL loader
was not compatible with this kit in testing; its presence alone does not make
that loader suitable for this image.

1. Mount the image as physical drive 0 and make the drive ready.
2. Load `rte-2100s-boot.abs` through the paper tape reader using a binary loader
   configured for SC **12**. The normal successful binary-loader halt is
   **HLT 77**. Alternatively, deposit the 53 words in `rte-2100s-panel.txt`.
3. Set **S = 000000** and **P = 000100**, then PRESET and RUN. The bootstrap
   reads the system from drive 0's fixed platter using SC **14/15**.
4. At `SET TIME`, press Return. The executive prompt is `*`.

The disk bootstrap's **HLT 11** means its disk-status error test failed.
The kit documents a possible initial `A = 140001` first-status indication;
continuing retries the seek/read. Other status values or repeated failures
need investigation against the physical controller's status and USB trace.

At the `*` prompt, enter:

```text
ON,FMGR
```

At FMGR's `:` prompt, `DL` lists SYS/AUX and the `IOTST` file. To load that
file into RTE's program table, type:

```text
RP,IOTST
EX
```

Press Return again to obtain `*`, then type:

```text
ON,IOTST
```

The expected output is `HP2100S RTE OK`. `RP,IOTST` is needed after each cold
boot because RTE reloads its generated program table. `ON,STATS` runs the
preinstalled system status utility. ASMB, FTN, ALGOL, EDIT, LOADR, SXL, and
FMGR are also installed by system generation.

For an interactive SIMH session, run from the output directory:

```sh
cd build/rte-2100s
"$HOME/simh/BIN/hp2100" boot.ini
```

## Verification and limits

The automated check starts a fresh 2100/32K simulator with all other
peripherals disabled, including both printer models, and optional FP/FFP
firmware disabled. It enables stops for unimplemented instructions, access
to unused select codes, and unreported I/O errors.

It boots through the generated tape, assembles `iotest.src.txt` with no
errors, links it with SXL with no unresolved references, writes the executable
to the SYS filesystem, loads and executes it, and runs STATS. A second fresh
simulator boots the saved disk, loads IOTST through FMGR, and executes it again.
Only then is the verified image copied to the SD-card layout.

This establishes SIMH operation and the image's byte layout. Physical
HP/FPGA/STM32 boot and the serial interface's electrical/timing behavior
still require the real-machine trial.

The [SIMH HP 2100 guide](https://opensimh.org/simdocs/hp2100_doc.html) documents
the 2100 model and 13210A/7900 support. `SOURCE-README.txt` in the generated
output preserves the restoration kit's provenance and original documentation.
