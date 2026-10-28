# CHECK sector-count acknowledgement

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
