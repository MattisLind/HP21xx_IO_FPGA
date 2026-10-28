# HP 13210 flag bring-up

The [CHECK investigation](check-data.md) compares the step34 failure with SIMH
and the original Verilog backend. SIMH passes the unmodified diagnostic;
its CHECK path supports DMA when requested. That behavior is now implemented
and installed on STM32; physical diagnostic retry is pending.

The [disk transfer timing experiment](transfer-timing.md) examines the normal
DMA and intentional-overrun paths after the physical step26 timing regression.

The [SEEK correction and validation](seek-validation.md) describes the current
production RTL, its request queue, and the diagnostic seek regression coverage.

The [RTE-II boot regression](rte-boot.md) boots the original disk image with
the production controller, starts FMGR, and checks `DL` and return to its
prompt at two seek delays. This also exercises CLC followed by READ while
positioning is still in progress.

The [HP2116 SEEK timing experiment](seek-timing.md) reproduces the hardware's
step 2 E21 in the full CPU simulation and records the command-flag, attention,
STATUS, and backend-capture ordering.

## Latest retest: E64 at initial status

After leaving configuration/custom-test entry (clear switch-register bits 2
and 3, then enter `EN` at H55), the user reported:

```text
H35 INITIAL STATUS IN STEP 01
E64 STATUS IS 000003 SHOULD BE 000000
H51 CYL 0000 HEAD 00 SECTOR 00 WORD COUNT 0000 UNIT 00
```

The HP status word is octal. In the implemented FPGA status-word layout,
bit 1 is data error and bit 0 is the aggregate error indicator. Thus `000003`
means **data error plus aggregate error**, not drive busy (HP bit 2).
The STM32 SET/CLEAR STATUS register uses a different packing: its data-error
mask is bit 0. Do not decode the HP word using the STM32 register masks.

The concurrent USB trace still shows unsupported commands (`??`, `E04`)
followed by `CM`. The installed firmware's unsupported-command path sets
data-error before completion, so it can account for this status. This is a
plausible software-generated error rather than evidence of an SD read failure;
the underlying cause of the unsupported command values remains unknown.
No new firmware has been downloaded. The prepared correction ignores such
commands without changing status or attention. This run stopped earlier than
the previous E21 seek failure and does not demonstrate a passing seek.

## Previous HP 2100S result: E21 during seek, with the STM32 disk backend

On 2026-10-25, after FAT mounting and all four images reported READY, the user
ran DSN 151302 with data select code 14 and command select code 15 (octal):

```text
H44 SEEK IN STEP 02
E21 MISSING OR DUPLICATE ATTENTION BIT
H51 CYL 0000 HEAD 00 SECTOR 00 WORD COUNT 0000 UNIT 00
```

The simultaneous STM32 trace showed `D3 ?? D3 E04 D3 CM`, then
`D0 ?? D0 E04 D0 CM`. Its earlier status report had
`commands=136 errors=136 trace_dropped=0`; those counters are historical,
not a count of this seek alone. `E04` here is a **STM32 unsupported-command
error**, separate from the HP diagnostic error numbers. FAT and image opening
have succeeded; successful disk transfers have not been established.

In `12960-18004_Rev-1805.src`, section 1 step 1 reads and checks initial drive
status; step 2 calls `FSEEK` to seek cylinder 0. Assuming no earlier errors were
continued through, initial status and the preceding setup checks passed. This
section has not yet reached its sector read/write tests.

`FSEEK` in `12960-18001_Rev-1805.src` calls `SEEK`, then `WAITS`, then checks
the captured command-channel attention word against the selected unit.
`GETN` in part 06 finds the rightmost set bit among the low four bits. Thus this
particular E21 path means no low-four attention bit was found, or the first
one found identified the wrong unit. Despite the general message's wording,
this path does not reject every possible multi-bit attention pattern. The raw
attention word was not captured, so missing versus wrong-unit attention is
not yet known. `WAITS` also reads status after capturing attention; reaching
E21 does not prove a correct seek completion or its subsequent status check.

Offline review found a difference from the reference STM32 testbench daemon:
the initial C++ backend responded to unsupported commands with data-error
status and attention/completion. The reference ignores them. That response
could introduce unwanted attention, so it has been removed and regression
tested. It does **not** explain why unsupported command values were received,
and is not yet a verified fix for this HP failure. The updated USB `?` report
retains raw CSR, command and RAR observations to help investigate that next.

Further candidates include FSMC reads when switching register addresses and
the relationship between the FPGA's RAR handshake flag, live command register
and the STM32's later seek attention. The reference HDL also contains the RAR
flag behavior, so it has not been changed on this evidence. The passing
single-register scratch test does not establish correct address switching or
full disk-command timing.

The programmers are disconnected. These corrections and diagnostic additions
are offline only; the hardware still runs the previously programmed firmware.

## Earlier E50 after correcting the select code

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

## Operations before the E50 halt

The following is the normal fresh-start path to the reported halt, with data
select code **14** and command select code **15**, both octal. A check is
described as passed **assuming E50 was the first error and no earlier error
halts were continued through**. Reaching E50 alone is not a saved transcript:
the diagnostic can report errors and continue depending on switch settings.

The controlling source is `12960-18003_Rev-1805.src`: startup at lines 55–116,
the presence check at 347–408, and `CTEST` at 525–612. The helper routines are
in `12960-18001_Rev-1805.src`: `SEEK`/`SEEH` at 580–605, `STAT`/`COMMD` at
607–638, `DADO`/`WAITD` at 640–661 and `WAITS`/`WAIH` at 667–701.
The reference binary also contains the flag/selection/interrupt tests at
`002724`–`003043`; this is not an inference based only on the error message.

### 1. Flags and selection, first 14 then 15

`H35` calls `CNVS`/`CTEST` first for the data channel, then for command.
For **each** channel it outputs an intentionally illegal disk-command word
(`M1024`, -1024 decimal, octal `176000`) without starting a disk operation,
then makes these explicit checks:

| Instructions/check | Expected result | Error if wrong |
| --- | --- | --- |
| CLF, then SFS | No skip with the flag clear | E2 |
| CLF, then SFC | Skip with the flag clear | E3 |
| STF, then SFC | No skip with the flag set | E4 |
| STF, then SFS | Skip with the flag set | E5 |
| Clear this channel, STF every other select code from 10 through 77, SFS this channel | This channel stays clear | E57 |

The last test excludes only the channel currently being tested. It therefore
checks both that 14 and 15 are independent of each other and that STF to other
codes in that range does not set their flags. It is a selection-isolation test,
not an exhaustive test of every command or data-bit pattern.

### 2. Command-channel HP interrupt handling

The data channel returns before this part; **command channel 15** executes it.
The diagnostic installs an interrupt trap instruction in location 15, sets
control and flag with STC/STF 15, and enables CPU interrupts. It deliberately
executes instructions that defer interrupt recognition, including indirect
JMP/JSB sequences. It then checks:

- An interrupt is received (otherwise E6).
- The interrupt's saved return address is the expected instruction boundary
  (otherwise E7). This verifies capture of the return address, not an OS's
  full interrupt-return procedure.
- Re-enabling interrupts after acknowledgement does not immediately generate
  another interrupt from the acknowledged request. The original trap-cell
  halt is restored before this check, so a spurious interrupt can halt there.
- After STC/STF 15, CLC 0 clears interface controls and suppresses the pending
  interrupt when CPU interrupts are enabled again.

Thus the run provides evidence for the HP command-channel interrupt path,
acknowledgement and control gating as well as flag/skip logic. It does not
test arbitration between simultaneously requesting peripheral cards, or the
STM32-side IRQ/DRQ connections.

### 3. Initial status queries and latched-status cleanup

The startup loops then visit all four drive numbers, 0–3:

1. `INST1`/`INST3` calls `STAT` and checks ready/busy. A ready-and-busy drive
   is polled again; a not-ready drive moves on without that wait.
2. `HLP2` reads each drive's status again. A ready drive would take the seek
   path; a not-ready drive takes `HLP3`, which issues **ADDRESS RECORD** through
   `SEEH` to clear latched status. This is not a mechanical SEEK RECORD.
3. `SEEH` sends a cylinder word on data channel 14, sends the alternate-position
   command (`130000` octal, command nibble B) on command channel 15, waits for
   the data flag, sends the head/sector word, and waits for the data flag again.
   The normal fresh-start values are zero cylinder/head/sector. A missing or
   late data response would produce E63/E11.
4. `WAIH` waits up to approximately 2 ms for command completion (E10 if absent),
   reads the command-channel attention word with LIA 15, then calls `STAT`.
   That attention word is stored here, not checked against a nonzero pattern.

Each `STAT` operation performs STC 14,C to prepare data input, OTA 15 with the
status command plus drive number, CLC 15 and STC 15,C to start it, waits for the
data flag (E12 if missing), then reads the status word using LIA 14. These are
actual command-output/status-input handshakes through the board. They do not
prove that all 16 data bits carry arbitrary patterns correctly.
Because all four units return the same not-ready condition and the initial
address arguments are normally zero, this also does not prove that drive
selection or nonzero cylinder/head/sector values are decoded correctly.

On the direct path with all four drives immediately not ready, these loops
perform **12 status requests and four ADDRESS RECORD sequences** before the
presence check. The presence check adds another four status requests: unit 0,
then alternatives 1–3. That is **16 status requests in total** on this path;
extra polling or a restart can increase the count. This is a source-derived
count, not a captured bus trace.

### 4. The first drive-presence check fails

`SCAL1` calls `SW2` before entering the selected disk-test section. `SW2`
finds not-ready set for unit 0, then finds no ready alternatives among units
1–3. It reports E50 and, with pass count zero, executes the observed HLT 6.

At this point **none of the five main disk-test sections has started** on the
normal path. There has been no verified sector read/write, DMA disk transfer,
CRC/data-pattern check, mechanical seek completion on a ready drive, or timed
DMA-overrun test. The successful work is nevertheless substantial: both
channels' flags and selection isolation, the command-channel HP interrupt
checks, repeated status transactions, and the not-ready initialization path's
two-word ADDRESS RECORD and completion handshakes.

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

## Standalone command-latch stimulus

Generate with `python3 scripts/hp13210_command_diagnostics.py`. Both variants
start at **076000**, use command select code **15 octal**, in the user-confirmed 32K-word memory, below the loader at 077700–077777.
The supplied DSN151302 tape loads only through 012402. Its source places the normal
read/write buffers after BUFB and the custom-test workspace at 016000
(up to the configurator / 020000 limit). Custom-test construction also consults
LWAM; do not rely on the standalone code surviving later custom-test editing.
The selected six/seven words at 076000 do not overlap the supplied diagnostic
load or the user-confirmed top-64-word loader. Neither issues STC, sends disk data, or
starts a seek/read/write. CLF 0 disables interrupts; CLC 15 clears interface
control. Interrupt state is not restored.

Start with [command-latch-hold.lst](programs/command-latch-hold.lst): it writes
`030000` (seek opcode, drive 0) once and stops at HLT 00, P=076005. This halt
is an inspection checkpoint, **not a hardware PASS**. A should be 030000.
Continuing executes a JMP back to the write sequence, not the literal data.

[command-latch-loop.lst](programs/command-latch-loop.lst) repeats the same
write until the operator halts. Enter its six listed words and set P=076000.
The default literal is at 076005 (076006 for the held variant). Changing this
literal permits other opcode/drive patterns without issuing STC. All values
in the listings are octal. Both have matching `.asm` and `.abs` artifacts.

To assess the hardware result, inspect the FPGA Command/status register through
STM32 FSMC at CPU address **0x60000004** while the HP holds this pattern. The
expected command nibble is **3**, drive **0**, protected/defective bits **0**:
`(raw & 0xF303) == 0x3000`. Abort bits 5:2 may retain earlier history and are
not part of that comparison. A returned HP attention word is not command
readback. USB `?` reports the last *dispatched* command, which this no-STC test
does not update; it cannot verify this test. Use a deliberate direct Command
read, not CSR (CSR reads acknowledge IRQ). No new firmware is needed.

Compare the held test with the loop to separate retained latch values from
transient timing. After either test, operator-halt the HP before inspection.
A successful result establishes only this register-write/read path; it does
not validate command IRQ capture, seek handshake, or disk operation. These
programs have passed offline flow/encoding/tape checks but have not yet run
on the HP. Existing serial capture remains active; no program has been sent
to the HP by the generator.

## One-shot standalone SEEK at 076000

Generate with `python3 scripts/hp13210_seek_diagnostic.py`.
[seek-once.lst](programs/seek-once.lst) contains 29 words at 076000–076034;
matching `.asm` and `.abs` files are provided. These replace only the earlier
standalone loop, below the top-64-word loader, not DSN151302.

The test uses cylinder/head/sector/unit all zero. Its I/O follows DSN151302
part01 SEEK/DADO/COMMD: OTA14, STC14,C; OTA15, CLC15, STC15,C;
SFC14 wait; OTA14, STC14,C; SFC14 wait. The helper calls, reporting, and
arithmetic for nonzero head/sector/unit are omitted. Unlike the complete DSN
path, no subsequent status command replaces the seek command.

After the second handshake, a private ISZ counter at076034 performs 65536
increments, providing extra settling time for the 4ms firmware worker. This
is deliberately longer than the diagnostic's initial 1ms attention poll;
it is not a calibrated timing test or an exact instruction-for-instruction
reproduction. Then SFS15 waits for command flag and LIA15 captures attention.
HLT00 at076030 (P=076031) is a checkpoint: A should be000001. CONTINUE
re-halts without issuing another seek. The program does not automatically
judge attention. Only076034 is written by the program; it returns to zero.

No timeout is implemented. If it keeps running, operator-halt and report P:
076010–076012 indicate the first data wait;076016–076020 the second data
wait;076025–076026 the command-flag wait. Do not single-step to evaluate
normal timing; enter/examine the listing, set P=076000, and run once.
No disk-sector data is written, no DMA is used, and CPU interrupts remain
disabled. Record A/P and the STM32 trace before changing the command register.
Offline tests exercise the I/O order, both outcomes of delayed flag polls,
missing acknowledgements, exactly65536 increments, and the private write range.
Hardware outcome is pending.
