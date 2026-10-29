# Step47 READ investigation

## Physical READ loss cleared; subsequent SDIO write underrun

With the address-qualified FPGA f3be9b..., the retained READ has1024 DATA
commits/events/HPinputs and zero addressF writes. The normal diagnostic later
stops at step46 WRITE, cylinder66/head1/sector16, status004103. Backend has
processed8111commands; last errorE08, drive0offline. The SD handle retains
error0x10 (TX FIFO underrun), distinguishing this storage fault from the earlier
FSMC write redirection. Full diagnostic acceptance is still incomplete.

A SRAM-only storage test changes SDIO from24MHz to4MHz, preserves the existing
2048bytes at imageoffset1632256 and rewrites identical contents1024times. Each
iteration syncs and verifies readback; all1024 pass, HALerror0. The firmware now
sets `SD_CLK_DIV=10U` so the polling driver has more time to refill its FIFO
while USB/SysTick interrupts run. Backend sanitizer tests pass. New firmware
build/program receipts and evidence are under `build/step47-investigation/sdio4-*`.

## Missing writes captured exactly — NADV glitch redirects address

The next physical run transferred954/1024. DATA commits/events/HPinputs954,
C++ position/length2048bytes. Histogram shows954 writes at DATA address4 and
**70 writes at addressF**, exactly accounting for all1024 software writes.
The recorder catches NADV and NOE both low for20ns as AD switches4->FFFF,
while NWE stays low. The unconditional address latch capturesF and restarts
the transaction decoder. Those writes never reach DATA.

The address latch and write-transaction rearm now both require two consecutive
50MHz samples of an address phase. A captured-waveform regression fails the
previous core and passes the new core across22 production variants. Board and
passive trigger tests pass. Both CPU step47 replays pass at scale9/poll200ns and scale19/poll8000ns.
The SRAM image f3be9b71740e1f1851f6a9fb34d0bb1db6415d057645c5517d6a1426f3053033
meets timing9.622ns. Hardware RAM test passed8192 jittered DATA writes/CSR
polls/mirror readbacks, zeroerrors and8192 commits/events. Clean image reloaded,
STM32 BIN verified/reset/run. Complete hardware acceptance remains pending.
Evidence: `build/step47-investigation/loss-recorder-run-trace.log` and decoded
`loss-recorder-run-trace.csv`; frozen stateC044, SRAM/histogram retained.

## Qualified-read physical rerun still fails

Physical step47 transferred935/1024, status000041. FPGA DATA commits,
completion events and HPinputs all935; C++ position/length2048/2048bytes.
The earlier old-flag-high trigger did not fire. Read qualification removes
the demonstrated false acknowledgment but does not solve the full diagnostic.
The remaining gap is89 software word advances without a decoded DATA commit.
Preserved `read-qualified-run-trace.log` and `read-qualified-run-backend-sram.bin`.
Further passive instrumentation will distinguish write-address misdecodes from
write transactions that never complete in the FPGA decoder.

## Captured false read acknowledgment — 2026-10-29

Latest physical step47:944/1024, status000041, cylinder0/head1/sector16.
Independent commit/event/HPinput counters all944 while C++ reaches2048bytes.
The256-sample recorder caught NOE low for20ns while NWE remained low during
a DATA write. The unqualified read decoder interpreted this as a read: dataIRQ
cleared and flag buffer set380ns before actual write completion. HP dataflag
rose340ns before completion, exposing the preceding word.

The read decoder now requires NWE high and a read window present on two
successive50MHz samples. This qualifies read side effects for CSR, DATA,
command/status, attention and seek record. The combinational read-output gate
continues to release immediately. The captured overlap is a permanent regression:
it fails the previous core and passes all22 timing/backend variants with the fix.
Both original CPU isolatedstep47 replays pass (CPUscale9/poll200ns,
CPUscale19/poll8000ns). Board/recorder tests pass and ISE minimumperiod7.238ns.
Recorder FPGA9ba36674... installed intoSRAM, unchanged STM32flash verified and
reset/run, FAT/all4READY. This is a confirmed fault; complete physical
diagnostic acceptance is pending.
Evidence: `build/step47-investigation/target-run-{trace.log,waveform.csv,backend-sram.bin}`.

## Latest physical result: step47 still fails

The fresh run with USB continuously connected fails step47 READ with966/1024
words and status000041. Passive staged/input/STC counters each966, flag-busy36,
CLF overlap0, IRQ-full0; actual C++ retained position/length2048/2048 bytes.
The address/data capture correction is therefore incomplete as a solution to
the diagnostic failure, despite passing the standalone bus tests. Evidence
`build/step47-investigation/fresh-retest/`.

A targeted measurement-only FPGA image809a8bbe... is now installed. It adds
independent per-READ commit/event counts (not gated by command-completion
attention), and captures256 samples of AD, FSMC controls and HP flags around
a flag-busy event in the failing cylinder0/head1/sector16 READ. Protocol logic
is unchanged from the stable-release fix. All22 protocol variants and the
mirror/counter/trace unit test pass; ISE7.595ns. A targeted diagnostic rerun is
pending. Collect it without reset using `read-target-trace.tcl`; the older
`read-counters.tcl` interprets this image's debug bank incorrectly.

## Confirmed FSMC fault and installed correction

The current fix addresses FSMC write capture, not READ cylinder length.
A guarded-image run transferred128/128 words but failed step26/E47: data
word35 was000004 instead of137752. Halted SWD scratch stress reproduced
address substitution:3/512 writes returned000E. A two-sample *write-window*
qualification candidate was insufficient (65/8192 failures) and was rejected.

An on-FPGA circular waveform recorder then captured an actual bad write:
NADV rises while NWE is already low and AD still holds000E; after80ns, NWE
rises for one20ns sample as AD changes toF77F; NWE then goes low again for
the real data phase, ending about380ns later. The old core commits the
address000E at the brief release, then commits the real data later. The
write-once guard alone kept the wrong first completion. This explains the
extra completion-event susceptibility absent from idealized SIMH/SV bus models.
It does not prove every historical physical error had this same cause.

Production RTL now retains the pending write across a brief NWE release,
keeps sampling data when NWE is low, and commits only after NWE is high for
two consecutive FPGA samples. A per-address done latch prevents duplicate
completion; NADV address phase rearms. READ length/EOC and STM32 firmware
are unchanged. The permanent protocol test replays the measured release,
checks one DATA completion, correct DATA/attention/scratch values, and rejects
the old capture logic. All22 protocol variants and board/LED tests pass.

Installed instrumented fixed FPGA SHA256
9e623d704484c7a2d413aef7a1f78104f849f2c778d1fef7ab798514eb9a518f,
minimum period8.088ns. SRAM load/FSMC/reload, STM32 BIN flash verification and
reset/run completed; no STM32 or SPI flash programming. Same halted hardware
scratch stress now passes8192 write/readbacks with0 errors. STM32 resumed
without reset after stress, fresh FAT/all4READY/idle CSR/request and zero
commands/errors/dropped events. CPU/SV step47 replays pass at independent50MHz
FPGA clock with divider9/poll200ns and divider19/poll8000ns. These are SV
backend runs, not C++ executing in the CPU simulation.

User asked for another P002000/S000000 diagnostic run; physical diagnostic
acceptance remains pending. Current counter bank is again the original eight
passive counters (the waveform-recorder image was replaced). Source fix is
in production; instrumented fixed image remains installed. Production FPGA
503f63a2... (7.213ns) is built/validated but not installed; verified ready ZIP
is `build/step47-investigation/hp13210-fsmc-stable-release-ready.zip`. Waveform evidence `build/step47-investigation/fsmc-waveform.*`,
stress `release-scratch-stress.log`, source/test receipt `result.json`.

Physical run on 2026-10-29 passed step46 with corrected STM32 firmware,
then stopped at step47:

```
H46 READ IN STEP 47
E13 0953 WORDS TRANSFERRED 1024 EXPECTED
E64 STATUS IS 000041 SHOULD BE 000000
H51 CYL 0000 HEAD 01 SECTOR 16 WORD COUNT 1024 UNIT 00
```

The last eight sectors exactly fit the cylinder. The backend logged RD/EC/CM.
This does **not** yet establish that the READ boundary test is off by one:
READ stages a word, waits for continuation STC, and reports EOC only if a
continuation arrives after the last valid word. Final input/CLC should instead
stop requests. The lost 71 DMA words require explanation before changing EOC.

## Independent evidence

* Supported SIMH Release32, unmodified configured revision1805 diagnostic,
  P2000/S0: first step47 pattern/cylinder passes all six READs, each1024 words,
  final IOI/CLC/EDT on each, status000000, error count0, reaches P004342.
  `scripts/hp13210_simh_compare.py` now permanently checks this case. Its
  steps34/35/46/47 and section1 cases all pass.
* Existing production-controller/SV-backend replay passes the first six
  step47 reads at CPU_SCALE15. Runs to450ms do not reach step48 because
  step47 repeats across patterns/cylinders; reaching a time limit is not
  evidence of diagnostic failure or a complete step47 pass.
* Isolated replay using a SIMH step47-entry memory snapshot, zero first-pattern
  image, and independent50MHz FPGA clock passes six reads at CPU terminal
  counts1 and9. The19/31 runs initially have only70ms limits; these results
  are incomplete, not confirmed hardware reproductions. Scale31 also produces
  an early five-word timeout and needs separate harness/timing investigation.
* Original READ worker, unchanged, with validated production transport and
  the50MHz FPGA clock passes all six reads at terminal count1. At3 its short
  response timeout fails (three words); divider choice matters.
* Literal pinned original CPU/controller/backend replays at terminal counts
  0/1/3/7/15 did not demonstrate a step47 pass within70ms; at0 there is E14
  missing command flag. Do not claim the literal whole reference passed.
* Reference history commit `d855d26de24409d80c6c477ba08e271fe5de690b`
  reports one successful long pass, then step35 failure on the next iteration.
  It predates `06c060d5aad3b5678b2777c8f6763a8d2e376ed4`, which introduced CPU
  scaling. Its testbench uses a100MHz clock; the earlier CPU has no divider.
  The historical report is not a fresh successful replay on this host.

## Temporary passive-counter FPGA installed

No production handshake change or STM32 flash write. Temporary source/image:
`build/step47-instrumented-board/hp13210a_core.v` and `controller.bit`.
Base protocol is the installed step35 READ-CLC controller. Added counters track
DATA staging, selected HP IOI rising edges, accepted data STC falling edges,
staging while the old flag is high, staging during CLF, request while IRQ
already set, raw STC falling edges, and last-stage flag state. Raw STC includes
command-channel pulses, so it is not directly the data request count.

Debug read bank uses AD0x10..0x1E (CPU0x60000020..0x6000003C, stride4).
These reads have no CSR/DATA acknowledgment side effects. Snapshot retained
across subsequent status commands; new READ/CHECK or reset clears it.
Normal low register bank and scratch register remain unchanged.

All22 controller protocol variants, board/LED tests, dedicated counter and
side-effect tests PASS. ISE minimum period6.886ns meets50MHz. Dedicated test
also demonstrates a baseline lost-ready-event case: staging while old flag
is high, before CLF, loses the flag event. **Whether physical step47 encounters
that condition remains unproven.** Do not call this the physical root cause.

User confirmed HP halted. STM32 halted, temporary image loaded into SRAM,
FSMC checks passed, same image reloaded to clear test state, existing
17f81beb... STM32 ELF verified and reset/run. SPI flash untouched. Fresh FAT
mounted/all4READY, commands/errors/dropped0, idle CSR/request0000. Serial
captures remain `build/serial-logs/20261029T062605Z/`. Receipt and all evidence:
`build/step47-investigation/result.json` and its surrounding directory.

Next: user repeats normal diagnostic P002000/S000000, leaves HP halted.
Read counters with OpenOCD and
`build/step47-investigation/read-counters.tcl`, preserving the FPGA state;
this script halts STM32 without reset. Record counters with console and fresh
STM32 status, then resume STM32 with `resume` (not reset) after reading if needed.
A passing rerun on the instrumented layout alone is not proof of a fix.

## Counter rerun and bounded candidate — 2026-10-29

The next physical run stopped with936/1024 words and status000041. Retained
counters: DATA completion events1179, HP inputs936, accepted data STC936,
flag-busy177, CLF overlap0, IRQ already set0, raw STC937, last-stage flags0040.
SWD SRAM snapshot confirms actual C++ position2048 bytes/length2048 bytes,
head1/sector16, commands71/errors3. STM32 was resumed without reset after
preserving `physical-counters.log`, `backend-sram.bin`, and `backend-sram.log`.
These are distinct measurements: FPGA completion-event count1179 is not the
software word count1024. HP input count agrees exactly with the console.

A directed bus test generates two NWE excursions under a single latched NADV
address. Baseline counts two DATA completion events; a candidate write-done
latch permits one completion until the next NADV address phase. New address
rearms writes. This addresses a concrete duplicate-completion susceptibility,
but the exact physical NWE/NADV waveform has not been measured. Do not yet
claim it explains all observed excess events or fixes the physical failure.

The candidate is still isolated in `build/step47-instrumented-board/`, with
passive counters retained; production core files remain unchanged. Full22
protocol variants, board/LED tests pass; ISE minimum period7.130ns. Guarded
bitstream SHA25655b65dc8058a28d8a08ecd9f51a4b1d77d44a09f5bf651e0042b9251c3410fa7.
Previous counter-only bitstream retained under `counter-image/` in the evidence
directory. SRAM installed with STM32 halted, FSMC checks passed, reloaded.
STM32 BIN verified against0x08000000, reset/run; no flash programming. ELF
verify attempts returned failure before restart, so final verification used
BIN at flash addresses, avoiding ELF runtime RAM contents. FAT/all4READY,
commands/errors/dropped0, idle CSR/request0000. User asked for another normal
P002000/S000000 diagnostic run; acceptance pending.
