# HP ALGOL chess on the 32K-word HP 2100S

This builds **HP CHESS VERSION A, 10/26/73** from the ALGOL program and five
assembly modules in [Terry Newton's chessbcs.zip](https://newton.freehostia.com/net/oldcomp/hpgames/chessbcs.zip).
The sources are unchanged. Compilation, assembly, and linking all run inside
the [generated HP 29016D RTE system](../README.md), using ALGOL, ASMB, and SXL.
The archive's prebuilt BCS executable is not used.

The disk retains the 2100 CPU, 32K words, TBG/TTY/PTR/PTP on select codes
10/11/12/13 and the 13210 controller on 14/15 (octal), with no printer and no
optional FP/FFP firmware. Chess uses the console on LU 1; its listing/board
output on LU 6 also goes to the console. Its assembly-language rotates and
double-word operations use the 2100's standard EAU.

## Build

Generate the base RTE image first if it is not already present:

```sh
python3 scripts/rte2100s.py
```

Then compile and install chess into a new image:

```sh
python3 scripts/rte2100s_chess.py
```

The helper downloads the original archive and the supplied
[historical BCS build log](https://newton.freehostia.com/net/oldcomp/hpgames/chess_log.txt)
into `build/reference/hpgames/` when absent. It verifies the SHA-256 hashes
in `sources.json`, checks the base-image manifest, and copies the base disk
before making changes. Existing output directories are refused. Alternatives
are selected with `--base`, `--output`, `--cache`, and `--simh`.

The RTE build performs these steps:

1. Reserve 20 load-and-go tracks and run `ON,ALGOL,99` on `chess.alg`.
2. Run `ON,ASMB,99` on each of `chess1.asm` through `chess5.asm`, appending
   their relocatable code to the load-and-go area and punching individual
   object tapes.
3. Run SXL, `RELOCATE L.G`, and `SEARCH LIBRY` twice. The second scan resolves
   the formatter's software conversion routines; the final link has no
   unresolved symbols.
4. Store the linked RTE executable as the file `CHESS` in SYS.
5. Cold boot a disposable copy, load CHESS through FMGR, play two moves, exit
   normally, and run IOTST to check that RTE still operates.

The unchanged main program compiles with `ERRORS=000`; all five assembly
modules report no errors. The linked code occupies **030000–053100 octal**,
with base-page linkage at **001100–001540**. This fits the generated system's
background partition and leaves 10,623 words above the linked code before
the loader reservation.

## Files

The output is `build/rte-2100s-chess/`:

| File | Purpose |
| --- | --- |
| `rte-2100s-chess-package.zip` | Complete package with image, bootstrap, sources, objects and logs |
| `rte-chess.img` | Raw 4,988,928-byte 7900A image with CHESS and IOTST installed |
| `sd-card/hp13210.cfg` | Map the chess image to drive 0 |
| `sd-card/images/rte-chess.img` | Identical ready-to-copy disk image |
| `rte-2100s-boot.abs` | Same SC 14/15 bootstrap used by the base image |
| `rte-2100s-panel.txt` | Bootstrap for front-panel entry |
| `source/` | Original ALGOL/assembly files, documentation, archive and historical log |
| `objects/chess0.rel` | Newly compiled ALGOL relocatable object tape |
| `objects/chess1.rel`–`chess5.rel` | Newly assembled relocatable object tapes |
| `build.log` | Full compiler/assembler listings and SXL link map |
| `play.log` | Cold-boot and game transcript |
| `boot-chess.ini` | Interactive SIMH startup that loads and starts CHESS |
| `manifest.json` | Provenance, source/image/object hashes and verification results |

The image uses the existing emulator geometry and little-endian word format.
The original base image and package remain unchanged.

## Run on the HP 2100S

Copy `sd-card/` to the SD card, or update the existing configuration so that
drive 0 uses `rte-chess.img`. Reset the STM32 and boot with the supplied
bootstrap as described in the [base RTE instructions](../README.md).
At `SET TIME`, press Return. Keep the S register at zero to disable the game's
verbose diagnostic dumps.

At RTE's `*` prompt, type `ON,FMGR`. At FMGR's `:` prompt, enter:

```text
RP,CHESS
EX
```

Press Return again to get `*`, then enter:

```text
ON,CHESS
```

Enter `1` for a new game. At `CHOICE: (B=1, W=-1)`, the number selects
**the computer's colour**: `-1` makes the computer Black and lets you move
first as White; `1` makes the computer White and it moves first.

Use the square numbers printed beside the board. For example, enter `32`
at `FROM SQUARE?`, then `42` at `TO SQUARE?`. The verified sequence was:

| Human move | Computer reply |
| --- | --- |
| 32 → 42 | 85 → 65 |
| 35 → 55 | 97 → 76 |

Enter `0` at `FROM SQUARE?` to end the game, then press Return again to get
RTE's `*` prompt. Reload `RP,CHESS` after each cold boot.

For interactive SIMH play:

```sh
cd build/rte-2100s-chess
"$HOME/simh/BIN/hp2100" boot-chess.ini
```

The cold-boot game test uses the 2100 model with stops enabled for
unimplemented instructions, unused select codes and unreported I/O errors.
Both computer replies, board updates and normal return to RTE were tested.
Physical HP/FPGA/STM32 execution remains to be tried.
