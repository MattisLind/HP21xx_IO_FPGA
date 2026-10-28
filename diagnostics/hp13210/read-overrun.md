# Step35 READ overrun comparison

**Prepared update:** the READ-CLC fix is now in production RTL, tested and
built and installed into FPGA SRAM on 2026-10-28. FSMC checks passed;
unchanged STM32 firmware verified over SWD. All four drives READY and idle.
Installation receipt: `build/step35-download/install/installed.json`.
Physical retry now passes step35 and reaches step46 WRITE, where E64 reports
status000041 instead of000000. Evidence: `build/step35-download/install/retest/result.json`.
The complete bundle is
`build/step35-download/hp13210-step35-ready.zip`, with checksums and instructions.

The final implementation latches the STC classification through the pulse and
checks the command flag buffer as well as its flag flip-flop, covering backend
completion before HP ENF. All22 FPGA variants and board/LED tests pass. New
tests reject old RTL and combinational-only rejection. They also cover new
commands/reset, normal and final READ, completion during a held pulse, CHECK,
and simultaneous final WRITE/INIT STC+CLC without losing the word.

The production CPU/SV model passes steps1–35 with200ns and8us polling; normal
20us software response margin is unchanged. Native C++ sanitizer tests and ARM
build pass. ISE minimum period8.345ns meets50MHz. Compatible STM32 ELF/BIN/HEX
are included; the ELF is unchanged from installed CHECK-DMA firmware5c509335...
because this repair belongs in the FPGA. New controller SHA256:
`1c7f3790170f5b56724b706f539eac732951aac8b27703935d741f8b40f02b46`.
Physical step35 acceptance is confirmed by advancement to step46. The following sections preserve
the investigation and the earlier candidate's limitations.

The physical CHECK-DMA firmware update passes step34, then stops at step35:

```text
H46 READ IN STEP  35
E64 STATUS IS 000000 SHOULD BE  020001
H51 CYL 0000 HEAD 01 SECTOR 07 WORD COUNT 0030 UNIT 00
```

The investigation reproduces the missing-overrun behavior in both the current
CPU/SV timing model and the actual C++ backend. SIMH passes. The relevant
difference is termination of the READ data phase: SIMH handles the final DMA
CLC, whereas the installed FPGA does not handle CLC on the data channel. The widened
20us software response window then accepts the deliberately extra STC as a
normal continuation. Physical edge timing has not been measured; the exact
times below are simulation observations.

## Diagnostic operation

Revision1805 part04 sets a30-word READ at head1/sector7 and replaces `DMSP`
with a call to `OVJ`. Part02's `OVJ` sets expected status020001, waits for
the DMA flag, then calls `DADO`: OTA data followed by STC data,C. This extra
output/STC is deliberately issued **after DMA has finished**. The final READ
DMA cycle itself performs input plus CLC/EDT and does not issue another STC.

The earlier native READ-overrun test covered a50us late request, with empty
polls establishing a timeout beforehand. It did not cover this short-gap
request or the final DMA CLC. Its success therefore did not establish step35.

## Independent comparisons

| Case | Result | Relevant behavior |
| --- | --- | --- |
| Supported SIMH Release32, CPU2116 | Step35 passes; status020001; reaches step36 at004047 | Final DMA input carries CLC/EDT; later STC sets Overrun |
| Current CPU + production controller + SV timing worker, CPU_SCALE15 | Reproduces step35/E64, actual000000 | Extra STC accepted within20us; word31 staged |
| Actual C++ backend, sanitizer-backed probe | At10us: no Overrun,31 words staged. At50us: Overrun,30 words staged | Confirms the gap-dependent behavior is in the real backend too |
| Literal original Verilog CPU/controller/backend, step35 entry replay | E14 missing command flag, then E64; no pass | Original interface/setup still has unrelated problems under Verilator5.052 |
| Original READ worker with current controller transport, original CPU speed | Isolated step35 passes; reaches36 | Short timeout and delayed probe catch the extra STC |
| Isolated CLC-aware FPGA candidate, current timing worker | Steps1–35 pass with0.2us and8us polling | Rejects STC after READ CLC; leaves20us normal response window unchanged |

SIMH was run from P2000 with the existing configured, unpatched diagnostic
memory and disposable disks. Its step35 trace contains30 data inputs. The
last input has `IOI | CLC | EDT`; `dpd_interface` clears `dpd_xfer` on CLC,
and a subsequent STC while the controller remains busy sets `STA_OVR`.
The shared READ/CHECK sector worker can still finish the sector after data
transfers stop. This is independent of the software polling timeout.

The current Verilog model records:

```text
106749175 ns: final READ input with CLC
106756695 ns: extra STC from DADO
WORD step=35 dir=R position=30 gap_ns=9920
TIMEOUT step=35 dir=R position=31
E64 STATUS IS 000000 SHOULD BE 020001
```

The9.92us observation is measured from staging word30 through backend service
of the extra request; the HP STC follows the final DMA CLC by7.52us. Both fit
within the20us software window. The backend acknowledges that request and
stages word31 before entering its drain state, so no late request remains to
set Overrun. No further word is DMA-input by the CPU, but the backend has
incorrectly treated the extra STC as valid continuation.

The original READ worker uses an800ns wait, then waits3000ns and probes for
another1200ns. With the original CPU speed in the isolated replay, the final
DMA input/CLC occurs at156315ns, the first timeout at156795ns, and the extra
STC at157415ns. The second probe sees the request at160035ns and sets Overrun.
These settings are simulator-specific and are not suitable STM32 timeout values.

## Candidate and limits

An experimental controller under `build/step35-investigation/clc-candidate/`
latches READ's final data-channel CLC. A later STC before command completion
sets Overrun and is not forwarded as a valid CSR6 request. The latch resets
on a new command/reset; CHECK and WRITE behavior are unchanged in this narrow
candidate. It passes the original diagnostic through35 with both tested
polling delays and stops after word30, without shortening the20us window.

This is an investigation candidate, **not production code or an installed
bitstream**. It still needs permanent directed regressions for READ CLC,
normal final words, command completion, new-command/reset clearing, CHECK,
wide pulses and clock phases; then the normal controller/board/build checks.
In particular, the classification of a late STC should remain stable through
its pulse even if command completion changes concurrently. The candidate's
simple combinational suppression has not established that boundary case.

The supported fix direction is explicit handling of READ termination in the
FPGA, with late-request rejection while the sector closes. Simply reducing
the STM32 timeout would risk the earlier normal-READ timing regression; the
physical run observed normal READ responses up to17us. No hardware, firmware
or production HDL changed during this investigation, and physical step35
still fails with the installed images.

## Evidence and reproduction

`build/step35-investigation/result.json` records source/log hashes and case
results. Subdirectories retain SIMH command files/traces, the step35 memory
snapshot, literal-reference and original-worker replays, the C++10us/50us
probe, and the isolated candidate with normal/stalled-poll logs. The candidate
patch is `candidate-not-installed.patch`; it has not been synthesized.

The independent SIMH regression now includes an explicit step35 case:

```sh
python3 scripts/hp13210_simh_compare.py --out build/step35-investigation/simh-confirmation
```

These comparisons establish neither a passing physical step35 nor a full
diagnostic pass. Preserve the build evidence with the handover when migrating.
