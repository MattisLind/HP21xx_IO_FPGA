# HP 13210 flag bring-up

## Current HP 2100S result: E50 after correcting the select code

On 2026-10-24 the user corrected the diagnostic's **data select code to 14**,
so the command channel is **15** (both octal). The earlier 15/16 diagnostic
configuration was mistaken. The retest reported:

```text
E50 UNIT 0 MISSING-PRESENT        NONE
P=002560  A=000000  B=000040  M=002557  M DATA=102006
```

The original source, `12960-18003_Rev-1805.src`, labels this check `SW2`:
it calls `STAT` and tests `NRBIT` (not-ready, octal `000100`). If the selected
unit is not ready, it checks the other units 0–3 and prints the ready units.
Thus the message means **unit 0 is not ready, and no other unit was found
ready**. It does not establish that the physical interface card is absent.

After reporting E50, the program loads its pass counter into A. If this is
zero, it executes `HLT 6`. In the reference binary, that halt is at `002557`
and contains `102006`; P then advances to `002560`. The reported A=0 and
addresses match this path exactly. B is a working register after error
reporting, not a raw drive-status word.

This result is consistent with the current implementation: the FPGA core's
`RESET_NOT_READY=4'hf` initializes all four drives not ready, the status command
returns the selected drive's not-ready bit, and the STM32 test firmware has
no disk backend to bring a drive online. Do not clear that status merely to
get past E50; later seeks and transfers still need a functioning backend.

If E50 was the first error, the initial channel flag/selection tests completed
for both 14 and 15. This is evidence of progress beyond the earlier E3, not
full disk-controller acceptance or proof of every data bit and timing margin.
The old inference of a particular higher-channel fault is withdrawn because
it relied on the wrong diagnostic select-code configuration. The next useful
checks are the standalone 14/15 flag tests and FSMC register transport,
followed by implementing real drive status and command servicing in STM32.
No device access or programming was performed for this analysis.

## Earlier E3 report with the wrong diagnostic configuration

The first real-machine test reported:

```text
DSN 151302
E3 SFC FAILED WITH FLAG CLEAR-CHANNEL 16
P=012136  M=012135  M DATA=102001  A=3  B=4
```

All addresses, instruction words, select codes and halt numbers here are octal.
The diagnostic was mistakenly configured for **data 15, command 16**. The
correct configuration is **data 14, command 15**, as above. The earlier report
described the board as being in slot 15. The FPGA's two-second idle heartbeat worked; no response to
selection was observed. The board is now disconnected. No programming or
hardware access was performed during this investigation.

## What E3 actually establishes

The original assembly is in the user's
[Type 4 source archive](http://bitsavers.informatik.uni-stuttgart.de/bits/HP/HP_1000_software_collection/master-files/type-4.zip).
Members `12960-18001_Rev-1805.src` through `12960-18008_Rev-1805.src` contain
DSN 151302 revision 1805. Part 03 contains `CNVS` and `CTEST`; part 08 contains
the error messages and common halt. These sources are extracted locally under
`build/reference/hp-diagnostics/type-4-12960/`; the archive is kept outside
version control in `build/reference/hp-diagnostics/type-4.zip`.

The published diagnostic manual also identifies E3 as failure to skip after
clearing the flag: [13210-90004, table CDM-3, printed page CDM-12](https://bitsavers.org/pdf/hp/disc/7900/13210-90004_Cartridge_Disc_Memory_Diagnostic_7900_7901_13210_197301.pdf).

The source's relevant sequence, after substituting command select code 16, is:

```text
        CLF 16
        SFS 16
        RSS
E2      JSB ERROR       CLF or SFS failed
        CLF 16
        SFC 16
E3      JSB ERROR       SFC did not skip with flag clear
```

`SFC 16` should skip the following instruction when the flag is clear. E3
means that this skip did not happen. It does **not** prove that the FPGA flag
was set: an unselected or disconnected board, a missing SFC input, or a missing
SKF return produces the same result. A missing SKF can pass the preceding E2
test, because SFS is expected not to skip there.

The matching reference binary is
`hp2116_verilog/diagnostics/12960-16001_DSN151302_7900_01_CARTRIDGE_DISC.abin`.
Its channel template has CLF at `002733`, SFC at `002734`, and E3's
`JSB ERROR` at `002735`. These instructions are patched with the selected
channel at runtime. The common error halt is at `012135`, containing
`102001` (`HLT 1`), so P=`012136` matches the next instruction after that halt.
Immediately before halting, the error routine loads the error number into A;
A=3 is consistent with E3. B is a reporting-routine working register and does
not identify a flag state or select code.

The startup code calls `CNVS`/`CTEST` for data first, then command. With the
wrong 15/16 configuration, E3 on 16 tested a select code outside the actual
14/15 pair. It therefore does not establish a fault in the board's command
selection path. The instruction-level meaning of E3 above remains valid.

## Comparison with the original hardware

The supplied [13210-90003 hardware manual](../../requirements/13210-90003_13210A_Disc_Drive_Interface_Kit_May78.pdf)
contains the relevant circuit in **figure 5-2, printed pages 5-5/5-6, PDF page
31**. Its right-hand CONTROL PCA section shows separate data and command flag
buffers, ENF-controlled flag latches, DSEL/CSEL decoding, and four skip terms
combined into the SKF output. The FPGA's logical skip equation has the same
structure: selected SFS with a set flag, or selected SFC with a clear flag,
for either channel.

The schematic confirms the current connector assignments: IOG pin 15;
lower SCM/SCL pins 14/16; higher SCM/SCL pins 37/34; SFC pin 5; CLF pin 7;
STF pin 9; ENF pin 46; and SKF pin 12. It does not validate our wire-wrap
continuity, external receiver/driver levels, or synchronized response timing.

There is a separate behavioral discrepancy to review: section 4-5, printed
page 4-1 (PDF page 17), specifies that POPIO sets both channel flags. The
ported core's reset/POPIO path sets the buffers but clears the flags, then
requires ENF to set them. This must be checked against the original latch
circuit and reference model before claiming hardware equivalence. It does
not by itself explain this E3 after an explicit CLF. No HDL was changed on
the strength of this observation.

An idle heartbeat confirms clock/configuration activity. It does not test
selection. A single 100 ms selection pulse can also be missed visually; the
repeatable programs below make the comparison easier. Missing STM32 disk
firmware is not an explanation for failure of this basic flag test.

## Standalone tests

Generate the checked-in listings, assembly and HP absolute binary tapes with:

```sh
make flag-diagnostics
```

These programs start at **002000**. Load only one at a time, using the normal
HP absolute loader or entering the `.lst` words at the console. They overwrite
that memory area, including part of a previously loaded diagnostic; reload
DSN afterwards if needed. Set P to `002000` and run.

They disable CPU interrupts with CLF 0 and clear interface control with CLC.
They do not restore interrupt state. There are no STC, data-transfer or disk
commands. Stop at the reported halt; do not continue beyond the final PASS halt.

| Program/listing | Purpose | Result |
| --- | --- | --- |
| [flags-14.lst](programs/flags-14.lst) | 16 words: CLF/SFC, clear SFS, STF/SFS, set SFC on data 14 | HLT 00 passes; HLT 01–04 identify failure |
| [flags-15.lst](programs/flags-15.lst) | Same checks on command 15 | HLT 00 passes; HLT 11–14 identify failure |
| [flags-both.lst](programs/flags-both.lst) | Both channels, then cross-channel isolation | HLT 00 passes; HLT 21–24 identify isolation failure |
| [flags-both-delay.lst](programs/flags-both-delay.lst) | Same, with four NOPs after each flag change | Compare with undelayed result |
| [scope-clear-14.lst](programs/scope-clear-14.lst) | Repeated CLF/SFC on data 14 | Loops on success; HLT 01 on missing skip |
| [scope-clear-15.lst](programs/scope-clear-15.lst) | Repeated CLF/SFC on command 15 | Loops on success; HLT 01 on missing skip |

Each listing has matching `.asm` and `.abs` files in the same directory.
[manifest.json](programs/manifest.json) gives each halt's exact meaning.
The delayed test adds time between instructions; it does not lengthen the SFC
bus pulse or prove that SKF reaches the CPU before its sampling point.

Start with the two independent 16-word tests and record the halt word and P.
The scope loop halts on the very failure being investigated. For continuous
probing despite a missing SKF, replace its `002004` word (`102001`, HLT 01)
with `000000` (NOP). Both skip outcomes then reach the loop's JMP. This modified
loop provides activity but no pass/fail verdict; stop it from the console.
Rapid repeated selection may make the activity LED look almost continuously
lit rather than show distinct blinks. Compare that with the idle heartbeat.

## First measurements when the board is available

Compare channel 14 and 15 using the corresponding loop. Under the **current
wrapper convention**, selected receiver outputs below must be low together
while IOG is active; asserted SKF is low at the FPGA's driver-input pin.
Those are implementation expectations, not measured hardware facts.

| Signal | HP connector | Receiver/driver channel | FPGA pin |
| --- | --- | --- | --- |
| IOG | 15 | B1RI3 | P33 |
| Lower SCM | 14 | B1RI2 | P34 |
| Lower SCL | 16 | B1RI4 | P32 |
| Higher SCM | 37 | C2RI3 | P5 |
| Higher SCL | 34 | C2RI2 | P7 |
| CLF | 7 | A1RI2 | P46 |
| SFC | 5 | A1RI1 | P48 |
| SKF | 12 | A2DO4 | P40 |

Trace from connector to receiver output to FPGA input, then from FPGA SKF
through the driver back to the connector. If both channels select correctly,
check SFC reception, flag clearing, SKF polarity and CPU sampling time in that
order. The 50 MHz port adds synchronization latency; the existing 200 ns
simulation cases do not measure the real HP 2100S sampling margin.

## Offline verification

The generator's instruction-flow model checks successful paths and injected
missing-skip, stuck-skip, stuck-flag and cross-channel faults. Unit tests also
check instruction encodings and absolute-tape record/checksum integrity.
`make test` includes these checks and the existing FPGA simulations. These
programs have not yet run on the real HP, and the model is not a CPU or bus
timing simulation. No FPGA or STM32 download is required to generate them.
