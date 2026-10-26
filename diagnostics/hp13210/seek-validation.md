# SEEK completion correction and validation

The controller now requests backend service when a SEEK address is accepted,
and raises the HP command flag when the backend writes completion attention.
ADDRESS RECORD still completes immediately after address acceptance.

Extending DSN151302 beyond step 2 exposed related problems that are included
in this correction:

- STATUS during a seek preserves the seek's completion attention. The earlier
  abort behavior made step 21 fail with E10 after the flag correction.
- Attention-suppression selection follows the addressed drive. CRS suppresses
  attention for all outstanding drives; CLC suppresses it for the selected
  seek. Neither cancels the drive's positioning operation: movement continues
  to the requested cylinder and Busy clears when positioning finishes.
- Busy starts when the final address word is accepted, without waiting for
  the STM32 polling loop (HP manual paragraph 3-45).
- Data acknowledgements survive the overlapping STC and later CLF phases of
  STC,C. Wider CPU strobes previously lost the second-word acknowledgement.
- Backend requests retain their command and RAR instead of reading mutable
  live registers after a later STATUS. An eight-entry queue preserves ordered
  requests from multiple drives and closely spaced seeks. Overflow sets
  overrun and preserves accepted packets.
- The STM32 backend retains Busy after a seek-while-busy error and waits for
  the original worker to signal completion. This prevents a following valid
  seek from being rejected by a worker that was still running. Invalid
  addresses complete immediately and clear the internal seeking state.

The request register addresses remain unchanged. On a CSR read with bit 7
set, one packet is consumed. COMMAND and RAR then describe that packet;
reading RAR releases the snapshot. Abort bits always reflect live state.
The existing STM32 firmware already reads CSR, COMMAND, then RAR. It requires
no behavioral change for this protocol. The simulated daemon drains queued
packets instead of waiting for IRQ to fall after the first one.

The internal name `seek_aborted` refers to suppression of completion attention,
not cancellation of head movement. The backend's independent per-drive worker
always runs to its deadline. A READ/WRITE to that drive waits for positioning;
other drives can proceed independently. Paragraph 3-22 says the interface is
free for other operations after the second address word is accepted; CLC
clears the command control flip-flop before another STC,C (paragraph 3-7 note).

The local [HP interface manual](../../requirements/13210-90003_13210A_Disc_Drive_Interface_Kit_May78.pdf)
describes delayed SEEK completion in paragraph 3-22, concurrent drives in
3-22, busy-seek and invalid-address checks in 3-23, and Busy timing in 3-45.

## Regression coverage

`make controller-sim` covers 22 combinations of backend enable, HP pulse
width/phase, chip-select handling, and early FSMC writes. Added checks cover:

- Completion flag/attention ordering on all four drives.
- Maximum valid cylinder/head/sector retention.
- Immediate ADDRESS RECORD completion without a SEEK backend request.
- STATUS, explicit CLC, per-drive isolation, and CRS during pending seeks.
- Overlapping STC,C phases and delayed CLF.
- Ordered requests from four drives despite later STATUS, packet consumption,
  return to live register reads, queue capacity, and overflow preservation.

The real C++ backend's sanitizer tests additionally exercise all four drives,
all heads, cylinder 0/202 and sector 0/23 boundaries (64 valid combinations),
and invalid cylinders 203/255 and sectors 24/31 (16 invalid combinations).
Existing overlap, abort, and microsecond timer-wrap tests also run. A new
busy-error recovery test checks that attention stays clear until the original
deadline and that the following valid seek succeeds. Seek tests
verify that positioning does not read or write sector storage.

Board/LED simulations and the 22 Python validation tests also pass. ISE
implementation passes the 50 MHz constraint; the measured minimum period is
5.751 ns. No hardware programming is part of this validation.

## Full CPU diagnostic checks

The original DSN151302 binary is configured and run by the HP2116 CPU model,
with the production controller core and no experimental flag override.
Validation runs through section 1 steps 1, 2, 21, 22, and 23, stopping on entry
to step 24. The final recovery checks continue through that step's valid SEEK
and stop before executing the first WRITE. This checks initial status, normal
seek attention, STATUS while busy, invalid cylinder, a second seek during
positioning, and recovery with a subsequent valid seek. It does not
constitute a complete disk diagnostic or a read/write acceptance test.

The simulator worker publishes Busy synchronously before starting its timed
worker, matching `Backend::dispatch`. The reference originally did this in
the forked worker, which could race a later seek-error completion. Added
capture delay is applied when servicing a new IRQ burst; an existing backlog
is drained without repeatedly injecting the same artificial scheduling stall.
These model changes preserve the diagnostic's checks.

All six final seek/recovery cases pass:

| Case | Seek delay | Added capture delay per IRQ burst | CPU speed |
| --- | --- | --- | --- |
| `seek500` | 500 us | 0 | Reference |
| `seek4000` | 4000 us | 0 | Reference |
| `capture20` | 500 us | 20 us | Reference |
| `capture2000` | 500 us | 2000 us | Reference |
| `seek4000-capture2000` | 4000 us | 2000 us | Reference |
| `cpu15` | 500 us | 0 | Eight times slower, wider I/O strobes |

Each final case starts from the initialized section-1 checkpoint produced by
a preceding normal diagnostic run and checks the recovery SEEK in step 24.
`build/hp2116-seek-validation/recovery/acceptance.json` records the runtime
settings and hashes of RTL, backend, checkpoints, and logs; its sources match
the successful ISE and ARM build receipts.

`scripts/hp2116_seek_timing.py --out build/hp2116-seek-validation/recovery`
prepares the instrumented sources. The normal run saves `configured.hex` at
the diagnostic's initial HLT 74 and `section1.hex` after startup has initialized
the diagnostic globals. `+FAST_MEM=<configured.hex>` replays the diagnostic
entry with reset peripherals. For CPU strobe tests, use
`+SECTION1_ONLY +FAST_MEM=<section1.hex>` to enter the original section-1
routine at 003137 octal without repeating long console/startup delays.
Using `configured.hex` for the section-1 entry would omit required startup
initialization and is not a valid test.

Use `+STOP_AFTER_SEEK_STEPS` to stop on step 24. The acceptance marker is
`PASS: DSN151302 section 1 steps 1, 2, 21, 22, 23; entering step 24`.
A time limit, a successful process exit, or a marker that merely reaches
cylinder 1 is not sufficient evidence of passing these tests.

Final recovery runs instead use `+STOP_BEFORE_FIRST_WRITE` and require
`PASS: DSN151302 seek steps and recovery seek in step 24; first WRITE not executed`.

The historical failure experiments and their raw traces remain described in
[seek-timing.md](seek-timing.md). Final production-code evidence is stored
separately under `build/hp2116-seek-validation/recovery/`. Earlier
`acceptance/` runs establish the RTL seek checks before the final backend
busy-error recovery correction.

The STM32 recovery correction has also been built for ARM and passed native
ASan/UBSan tests. On 2026-10-26 both updated images were installed: the FPGA
over JTAG into volatile SRAM, and the STM32 into flash after a verified backup.
FPGA FSMC scratch/attention readbacks pass; STM32 USB reports FAT mounted,
all four drives READY and zero errors. Physical diagnostic acceptance is still
pending. FPGA SPI boot flash remains unchanged, so power cycling requires
another FPGA SRAM download. See `build/hardware-update-20261026.json` and
the current hardware section of `HANDOVER.md` for image hashes and logs.
