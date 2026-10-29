# Experimental per-drive SEEK capture

Branch `fpga-rework-experimental` starts from the `working` tag. The tagged
hardware passed four long diagnostic passes on unit 0, heads 0/1, with zero
errors, before an orderly switch-register-bit-15 halt (`102004`, P001434).
This branch changes request capture, not the FSMC waveform fixes or STM32
firmware. On 2026-10-29 the installed candidate completed two recorded long
passes with zero errors on unit 0, heads 0/1; the user confirmed it worked.
The subsequent [code review](code-review.md) identifies further cleanup and
corner-case work without changing the installed candidate.

## Capture rules

There is no command FIFO, head/tail pointer, occupancy count, or overflow path.

* Each of the four drives has one pending destination and one valid bit.
  Accepting its first SEEK asserts Busy immediately. A later SEEK while Busy
  changes the live RAR head/sector and sets Seek Check, but does not replace
  the original destination or start another positioning operation.
* One separate command/address slot holds a controller data operation.
  Command-channel CLC or CRS cancels it if STM32 has not consumed it. Accepted
  drive seeks survive CLC/CRS; existing per-drive abort bits suppress their
  completion attention without cancelling positioning.
* CSR read-start selects pending seeks in drive order 0..3, then the ordinary
  command. Different drives do not require FIFO ordering. A consumed seek slot
  can be reused when its drive is no longer Busy.
* CSR snapshots COMMAND/RAR and the returned IRQ bits together at read
  start; reading RAR releases the packet snapshot. CLC or a new command during
  a CSR read cannot change the packet or consume a previously unseen arrival. Live attention-suppression bits remain visible. STM32 register
  addresses, transaction sequence, and firmware stay unchanged.

Seek Check is cleared by a newly accepted non-busy SEEK. The MCU's later
Seek-Check-only clear cannot erase a newer busy-SEEK error while Busy remains
set. Explicitly clearing Busy and Seek Check together still works, including
backend initialization. A simultaneous busy-SEEK error takes priority over
an older backend clear.

These rules follow interface manual paragraphs 3-22/3-23: the interface is free
once the second seek address word is accepted; drives position independently;
a second seek to a positioning drive retains its original cylinder. SIMH's
per-drive scheduled units model the same division of responsibility. The
original eight-entry FPGA FIFO was a delivery buffer for delayed MCU polling,
not a feature of the HP interface.

## Verification and tradeoffs

The permanent controller regression covers all 22 timing/backend variants.
Mailbox-specific cases cover four pending drives, reverse arrival order,
mutable live registers, an additional data command, second-seek rejection,
late MCU status clearing, slot reuse, atomic CSR reads across CLC/new arrivals,
and CLC cancellation/replacement of an
ordinary operation while a drive seek survives. Existing attention, CRS,
invalid-address, DMA termination, and measured FSMC-glitch checks remain.

Original-CPU SEEK/recovery tests use seek delays 500/4000 us, capture delays
0/20/2000 us, and the slower CPU divider. Separate step-47 READ replays use
CPU divider9/poll200ns and divider19/poll8000ns. RTE-II boot/FMGR directory
regressions exercise CLC followed by READ while positioning is in progress.
All22 controller variants, all eight CPU cases, both RTE-II cases, and
board/LED tests PASS on the final source. Results and source hashes are recorded
under `build/queue-review/experiment.json`, `cpu-results.json`, and
`rte-boot-final/acceptance.json`. A source/bitstream/timing/receipt package is
`build/queue-review/seek-mailboxes-ready.zip`. These checks preceded programming;
installation and the two physical long passes are recorded in `HANDOVER.md`.

The final ISE comparison uses the exact `working` production core and identical
board sources/pins/toolchain (no passive recorders):

| Mapped result | Working FIFO | Per-drive slots |
| --- | ---: | ---: |
| Slice registers | 392 | 395 |
| Slice LUTs | 449 | 453 |
| LUTs used as memory | 32 | 24 |
| Occupied slices | 191 | 190 |
| Minimum period | 8.233 ns | 7.435 ns |

Both meet the 20 ns clock constraint with zero timing errors. This is an
architectural simplification with essentially unchanged FPGA area, not a
large resource reduction. More explicit seek/error/cancellation handling also
means the source has more lines than the compact generic FIFO implementation.
The first mailbox prototype was slightly larger; the final version removed
ordinary-command overflow logic by modelling CLC cancellation instead.

Build artifacts are `build/queue-baseline-board/` and
`build/queue-mailboxes-v3-board/`. The latter is experimental and must not be
confused with the image that produced the four hardware long passes.
