# Disk transfer timing experiment

The physical DSN151302 run with a six-microsecond firmware response deadline
failed at READ step26: status020001 instead of000000 and a word8 data mismatch.
STM32 logged two short WR transfers, then RD/TO/OV. The earlier100-us deadline
had reached step32 but failed to recognize its deliberately late third word.

The prepared correction separates three waits:

| Wait | Value | Purpose |
| --- | --- | --- |
| Initial READ/WRITE/INITIALIZE data | 100us | Let the diagnostic observe DMA starting before a short transfer finishes |
| First WRITE word / CHECK count | 100us | Allow initial setup independently of subsequent response timing |
| Subsequent WRITE / READ response | 20us | Tolerate polling/service delays while rejecting the deliberately late word |

The initial delay starts after command handling and any image read. It is a
software startup guard, not a measured mechanical/rotational disk model.
SEEK remains500us and CHECK remains autonomous after its count word.

The manual's paragraph3-61 specifies5.9us from the **data channel flag**. That
does not give a safe deadline for untimestamped firmware CSR samples. The
backend now accepts an already-pending word before checking the deadline:
only an expired **empty** poll establishes the end of the accepted prefix.
Words arriving after that cutoff are discarded during sector closing and set
Overrun. Sector closing still uses6.4us/remaining word, preserving the accepted
WRITE prefix and zero-filling its tail. A long interrupt can obscure whether a
pending word was late; precise enforcement would require hardware timestamps.

## CPU experiment

`scripts/hp2116_transfer_timing.py` generates an isolated copy of the pinned
HP2116 CPU testbench, using the production HP13210 RTL and original DSN151302
binary. It replaces the SV daemon's transfer tasks with parameterized waits,
late-word discard and sector closing. CHECK is updated to accept its sector
count autonomously. Disk images exist only in RAM and are never saved.

This experiment uses the **SV daemon, not the C++ backend or ARM firmware**.
Actual C++ tests separately verify the startup delay, timer rollover, delayed
polls, jittered data integrity and deliberate READ/WRITE overruns.

The initialized section1 checkpoint comes from the earlier full diagnostic
configuration/startup run. Each case gets reset peripherals and its own output
directory. CPU_SCALE15 and31 are eight and sixteen times slower than reference;
these are timing stress settings, not calibrated HP2100 speeds.

With immediate data service, the two-word step32 write can finish before DMAT
first reads its word count. DMAT then takes its long fallback loop rather than
the intended short delay. A third word arrives after command completion,
reproducing step32/E64 status000000. The100-us initial delay prevents this race.

The final cases require explicit diagnostic progress markers, not merely a
successful process exit or simulation time limit:

| Case | CPU_SCALE | Poll delay | Required result |
| --- | --- | --- | --- |
| Normal and overrun | 15 | 0.2us | Original checks through32; late third WRITE discarded |
| Normal and overrun with stall | 15 | 8us | Same checks through32, including READ26/27 and CHECK30 |
| Slower normal DMA with stall | 31 | 8us | Original checks through27, including data verification |
| Six-us failure control | 15 | 8us | Normal step24 WRITE prematurely closes after one word; subsequent words are late |

CPU-model timing records expose each word's observed response and the late
third word's gap. The injected8-us poll delay represents a service stall, not a
measurement of the physical STM32. A20-us wait has margin for this stall while
remaining below the deliberately late response in the selected CPU settings.
It is not expected to fit arbitrary CPU speeds with no corresponding scaling.

Recorded normal response maxima were2.68us WRITE /2.44us READ with0.2-us
polling, and8.72us WRITE /8.48us READ with8-us polling. The third WRITE in
step32 was discarded at an observed24.04us or20.48us gap respectively. These
include polling/FSMC timing; they are not the physical HP's response times.

These are bounded transfer tests, **not a full section1 or diagnostic pass**.
Exploratory slower-CPU runs beyond this range stalled around REFINE/CHECK;
their causes have not been resolved. The native backend additionally checks
the READ-overrun behavior needed by step35; the CPU experiment stops before it.
RTE-II has not been rerun with this timing model.

## Reproduce

Requires the existing Verilator Docker image and the initialized checkpoint at
`build/hp2116-seek-validation/recovery/section1.hex`. Prepare/build/run all four
cases from the repository root:

```sh
python3 scripts/hp2116_transfer_timing.py --out build/transfer-timing/final --run
make stm32-disk-test
make stm32-disk-build
```

The CPU receipt is `build/transfer-timing/final/acceptance.json`, with exact
runtime options, source/generated-file hashes and per-case log hashes. Native
and ARM results are under `build/transfer-timing/`. Hardware programming is
separate; build success does not establish physical diagnostic acceptance.

The USB status report now includes maximum observed READ and WRITE response
times. These retained maxima include polling/service delay and are not HP
edge timestamps. Use them with the next physical diagnostic result when
deciding whether the20-us setting needs further adjustment.
