# CHECK sector-count acknowledgement

**Current status:** the optional CHECK DMA repair passed step34 on the HP.
The fresh run now halts at step35: READ-overrun status000000, expected020001.
The optional CHECK DMA repair is installed on STM32 and the rebuilt FPGA is in SRAM.
The earlier claim that the diagnostic itself was defective was wrong.

Physical evidence: `build/check-step34/check-dma-update/retest/`. A fresh H0
banner is followed by step35/E64 at cylinder0/head1/sector7/count30, with no
step34 error. STM32 reports41 commands, only the two expected seek errors,
READ response maximum17us, WRITE3us, final READ/TO/CM without OV. No hardware
changes during this check. Full diagnostic acceptance remains failed at35.

## Installed repair

CHECK accepts its six-bit sector count, reads the bounded image range, waits
the normal100us startup guard, then offers data to the HP. The stream uses the
same20us response window as READ. If DMA stops, CHECK finishes its independent
count/EOC operation without timeout or Overrun. Completion retains zero drive
attention. Exact count-to-boundary succeeds; requesting beyond it sets EOC.
Zero count remains a no-op. Media read failures use the existing quarantine
and error path. A command captured while CHECK is active stays queued.

The FPGA retains the count-acknowledgement gate. It raises a data flag when
firmware actually stages a word, allowing CHECK DMA without a stale first
transfer. No functional RTL change was needed; the permanent regression now
checks staged CHECK data, its value, and the next-word request/acknowledgement.

Validation: actual C++ sanitizer tests PASS, including DMA128/count50, no-DMA,
partial/count-end streams, all existing boundary cases, rollover, media errors
and pending commands. The old backend fails the new tests. All22 controller
variants and board/LED tests PASS. Updated CPU/SV model passes steps1–34 with
200ns and8us polling; it does not execute the C++ firmware. ARM build uses
48256 flash bytes/22716 RAM. ISE minimum period7.543ns meets50MHz.

Installed STM32 ELF SHA256:
`5c5093355bca40b0ded0a86a209554dcbd855b70b7281bb93a7872f1fd1f3e81`.
Rebuilt FPGA SHA256:
`1557ca2fafc7f8e5ad8c1d8c4640e8ac14b6a3da533b59a6fad5da4f96a9a6bd`.
FPGA was loaded with STM32 halted, scratch/attention readbacks passed, then
the same FPGA image was reloaded to clear test state. STM32512KiB flash was
backed up and verified before programming/verification/reset. SPI flash was
untouched. Fresh USB confirms FAT/all4 READY, zero commands/errors/dropped
and idle CSR. Evidence: `build/check-step34/check-dma-update/` and
`build/stm32-disk/programmed.json`. Physical acceptance remains pending.

## Earlier failure and count-flag correction

The physical DSN151302 run with the100us initial data delay and20us response
wait passed the earlier READ26 and intentional WRITE-overrun32 failures, then
halted at step34:

```text
H22 CYCLIC CHECK IN STEP  34
E13 0001 WORDS TRANSFERRED  0128 EXPECTED
H51 CYL 0000 HEAD 01 SECTOR 21 WORD COUNT 0128 UNIT 00
```

The STM32 had accepted40 commands, with only the expected invalid-seek and
busy-seek errors. Maximum observed normal response times were READ6us and
WRITE3us. Its final CHECK command set the expected end-of-cylinder status.

The FPGA asserted the HP data flag after every backend DATA-register read.
That is necessary to request the next word during WRITE/INITIALIZE. For CHECK,
the read instead consumes the single sector-count word; requesting another
word lets the diagnostic's armed DMA transfer one unwanted word.

The production fix suppresses the backend-read contribution to the HP data
flag while the live command is CHECK. It preserves the CSR bit6 acknowledgement
and the command-channel completion flag. READ staging and WRITE/INITIALIZE
acknowledgements retain their normal data requests. No register map or STM32
firmware change is needed.

The [interface manual](../../requirements/13210-90003_13210A_Disc_Drive_Interface_Kit_May78.pdf),
paragraphs3-28/29, describes CHECK as accepting a sector count and examining
sectors without transferring their data to the computer. Command completion
sets the command-channel flag.

`fpga/hp13210/tb_hp13210a.sv` now tests CHECK, READ, WRITE and INITIALIZE
acknowledgements together. The new assertion fails on the earlier RTL.
`make controller-sim` applies it across the existing22 pulse/phase/backend
variants; each enabled variant verifies that:

- CHECK count consumption clears CSR bit6 without setting HP SRQ.
- READ/WRITE/INITIALIZE still request the next DMA word.
- Command/RAR capture and count data remain correct.
- A zero-attention completion still raises the command-channel flag.

Original physical evidence and isolated old/new-RTL reproductions are under
`build/check-step34/`. Permanent regression/build/installation evidence is under
`build/check-step34/install/`. A passing RTL test is not physical diagnostic
acceptance; the next hardware run must confirm step34 and subsequent steps.

The full CPU experiment with the fixed RTL removes the extra word but still
reports step34/E13 with **zero** words transferred. It has not passed step34.
This remaining behavior needs investigation; the directed flag fix alone
must not be presented as complete diagnostic acceptance. The firmware timing
image is unchanged by this FPGA update.

The subsequent physical run reproduces that same zero-word E13 at step34.
STM32 again reports40 commands, two expected seek errors, response maxima
READ6us/WRITE3us and final CHECK/EOC/completion. The unwanted transfer is gone,
but the remaining CHECK/DMA-completion mismatch is unresolved. Hardware retest
evidence is in `build/check-step34/install/retest/`.

## Current-model failure trace — 2026-10-28

The remaining zero-word E13 follows when our current model leaves DMA incomplete.
Revision1805 part04, step34, sets `WCNT=128`, calls `DMR` to arm a READ in case
CHECK is misdecoded, outputs the sector count50, issues CHECK, then calls
`DMAT`, `STAT`, and `WEND`. It never calls `DMRFC`. The same omission is in
the locally archived revisions1432 and1644.

Part02's `DMAT` waits for the command flag, tests the DMA flag, and enters
`FTCX` when DMA is incomplete. `FTCX` sets bit15 of `DMRF`, stops DMA, and
converts the residual count to the number of transferred words. `WEND` calls
`WCHK`; even when status matches, `WCHK` calls `DMERQ` if `DMRF` is nonzero.
`DMERQ` reports E13 when bit15 remains set. Adjacent steps33 and36 explicitly
call `DMRFC` to remove this bit when incomplete DMA is allowed.

The unmodified CPU experiment confirms the actual binary takes this path.
All addresses and values below are octal, except word counts stated in prose:

| Address | Executed instruction / observation |
| --- | --- |
| 001540 | `SFS` command channel sees completion |
| 001542 | `SFC 06` sees DMA incomplete and skips the successful return |
| 001550 | `STA 000156` stores `100000` in `DMRF` |
| 001552 | `LIA 02` reads residual DMA count `037600` |
| 001555 | Adding `WCNT=000200` gives `040000`; masking with `017777` gives zero words transferred |
| 001356 | `XOR 000237` compares actual status `000041` with expected `000041`, giving zero |
| 001332 | `LDA 000156` finds `DMRF=100000` despite matching status |
| 001577 | `DMERQ` loads the still-set `100000` marker |
| 001613 | `SSB,RSS` takes the incomplete-DMA reporting branch |
| 001620 | E13 calls `ERROR` at simulated319.777ms |

The model's DMA count is14 bits; `037600` is the unchanged count for128
words, not evidence that any word transferred. Command completion is present,
so the timeout indicator stays clear. Status in this path matches the expected
end-of-cylinder result; the outstanding error is the incomplete-DMA marker.

This trace establishes our model's failure path. It does **not** establish a
diagnostic defect. SIMH demonstrates the missing behavior: CHECK can service
an enabled data channel and let DMA complete, while continuing its independent
sector-count/EOC operation. The original Verilog backend implements this too.
The diagnostic's intended distinction is that CHECK continues checking to EOC
after its128-word DMA finishes, whereas a misdecoded READ stops after DMA.
No diagnostic correction is appropriate on this evidence.

Reproduce the trace using the previously compiled production-RTL timing
experiment:

```sh
python3 scripts/hp2116_check_trace.py
```

The script records executed instructions and source hashes under
`build/check-step34/instruction-trace/`. It uses the SV backend, not the C++
firmware, and changes no diagnostic memory. The older installed CPU run and
physical capture independently report the same zero-word E13. This finding
does not establish a passing physical diagnostic or acceptance of later steps.

The340ms trace completed successfully as an investigation: it executed the
E13 call and printed `E13 0000 WORDS TRANSFERRED 0128 EXPECTED`. Its
`result.json` records that diagnostic acceptance failed. Python syntax and
`git diff --check` also pass; no hardware build or installation was performed.

## Independent SIMH and original-model comparison

The user's request to test independent emulators overturned the initial
diagnostic-bug inference. The CHECK opcode does not need a diagnostic patch.

| Experiment | Observed result | Scope |
| --- | --- | --- |
| GitHub SIMH HP2100 Release29, commit698dc8a1 | Reaches step35 with `DMRF=0` | Normal diagnostic restart atP2000 through34 |
| HP maintainer's supported SIMH Release32 | DMA count0, DMA flag1, `DMRF=0` atP004031 | Normal diagnostic restart through34 |
| Supported SIMH Release32, S001000 | Normal `HLT102011` at end of section1, no errors | Entire section1 |
| Original Verilog CPU, controller and backend | Step2/E21, halts with A000021 | Current Verilator5.052 checkpoint replay; not a full pass |
| Current CPU/controller/timing harness with ONLY original CHECK worker restored | Enters step35 at105.549ms, no error | Steps1–34; no diagnostic patch |

SIMH was compiled locally from the downloaded sources. Release32 came from
the [HP simulator maintainer's distribution](https://simh.trailing-edge.com/hp/).
All SIMH cases use CPU2116,32KW,EAU, 13210A at22/23, and four disposable blank
disks. They load the existing configured revision1805 memory checkpoint and
restart normally atP2000; they do not replay tape loading or patch instruction
words. The Verilog comparisons replay the same initialized section1 checkpoint.
The original CPU/controller files in the literal-reference case are byte-for-byte
copies; testbench additions select the entry point, log steps, stop the run and
disable image persistence. Its early failure does not invalidate a remembered
pass under a different simulator/setup, nor establish the cause of that failure.

The supported-SIMH trace records exactly128 data-channel input cycles between
the CHECK command and the subsequent status command. Its `SFC06` at001542
falls through to the successful return at001543. With our current backend,
the same test instead skips to001544 and reports incomplete DMA.

SIMH's `dpc_svc`, cases `FNC_RD`/`FNC_CHK1`, shares the read-data loop and
raises the data flag when `dpd.command && dpd_xfer`. CHECK sector counting
continues when handshakes stop. The original Verilog CHECK worker similarly
stages words while `got_word` remains true, then continues `calculate_rar`
without waiting for further data requests. In contrast, our current C++
`CheckCount` and generated SV CHECK worker consume the count and complete
without offering any data stream.

The reference distinction is therefore **optional DMA during CHECK, with
sector-count/EOC checking independent of DMA termination**. The manual's normal
no-transfer CHECK description was insufficient grounds for forbidding that
behavior. A repair must preserve no-DMA CHECK completion and support an armed
data channel. Restoring only the old count-acknowledgement flag gives one
stale word with the current backend and is insufficient.

Reproduce the independent comparison after building supported SIMH:

```sh
python3 scripts/hp13210_simh_compare.py
```

Original evidence: `build/check-step34/simh/`,
`build/check-step34/original-verilog/`, and
`build/check-step34/reference-check-worker/`. The repeatable script records
commands, traces, hashes and a receipt under
`build/check-step34/simh-confirmation/`. No production firmware/RTL or physical
HP memory was changed in these comparisons. Hardware step34 remains failed;
neither this comparison nor a section1 pass establishes full diagnostic acceptance.
