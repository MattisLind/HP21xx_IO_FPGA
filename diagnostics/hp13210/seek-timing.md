# HP2116 diagnostic SEEK timing experiment

This document preserves the original failure experiments. The resulting
production change and extended tests are described in
[seek-validation.md](seek-validation.md). New simulation copies use production
RTL directly; the old `COMPLETION_FLAG_ONLY` experimental override is retired.

The full HP2116 CPU simulation, running the original DSN151302 absolute
binary through its configurator, reproduces the real HP's section 1 step 2
E21. The controller in these experiments is the corrected board core from
`fpga/hp13210/hp13210a_core.v`, including its FSMC write fix and read mux.
No hardware programming was performed for these experiments.

`scripts/hp2116_seek_timing.py` prepares an instrumented copy under
`build/hp2116-seek-timing/`. It leaves the reference submodule unchanged.
The testbench's simulated STM32 worker is used, rather than compiled STM32
firmware. This tests the command/flag protocol and relative timing; it does
not establish the physical HP's instruction timing or MCU service latency.

## Reproduced failures

| Seek delay | Added command-capture delay | CPU divider | Result |
| --- | --- | --- | --- |
| 4000 us | 0 | 1 | E64 in step 1: status 000005, expected 000000 |
| 500 us | 0 | 1 | E21 in step 2; captured SEEK 0x3038, completion sees 0x003C and abort |
| 500 us | 2000 us | 1 | E21 in step 2; first backend command capture already sees 0x003C |

Both E21 cases halt with P=012136, instruction 102001, A=000021, B=000004,
matching the reported hardware stop. Values in that sentence are octal;
backend snapshots prefixed with `0x` are hexadecimal.

Authoritative logs for these cases are respectively `core-4ms.log`,
`core-500us.log`, and `core-late-capture.log` in the build directory.

The following comparisons reach the cylinder-1 seek in step 21, showing
that step 2 and its attention check succeeded:

| Seek delay | Added capture delay | Flag behavior | Result log |
| --- | --- | --- | --- |
| 50 us | 0 | Existing early flag | `core-50us.log` |
| 500 us | 2000 us | Completion-only flag experiment | `core-completion-only-late.log` |
| 4000 us | 0 | Completion-only flag experiment | `core-completion-only-4ms.log` |

The 50 us result shows that sufficiently short delay can hide the race.
The completion-only experiments preserve the original seek delays and
also tolerate slow backend capture: the HP waits for attention instead of
issuing STATUS prematurely. These are simulation results through step 2,
not full-diagnostic acceptance or confirmation of the actual controller's
required behavior for all commands.

In the delayed-capture completion-only run, the step 2 address handshake is
at 477268215 ns, command capture at 479268955 ns reads 0x3000, completion at
479770065 ns still reads 0x3000 with abort clear, and the HP flag rises at
479770275 ns with attention 1. The race is absent even though command capture
takes about 2 ms.

The eight-times-slower CPU experiment (`core-slow-after-config.log`, seek
500 us, capture delay 0, existing flag behavior) instead reports **E63 NO
DATA FLAG during startup, step 00**. Its first seek completes with abort
clear, but the HP does not reach the normal attention-read path. Changing
the CPU divider also stretches the I/O strobes and their relationship to
the controller's acknowledgement logic. This exposes a separate handshake
problem; the result must not be counted as a successful E21 timing control
or as a calibrated model of the real HP's speed.

## Step 2 timeline with a 500 us worker and immediate capture

Times are relative to the FPGA accepting the second SEEK address word.
They come from the full CPU execution, not a hand-written bus stimulus.

| Relative time | Event |
| --- | --- |
| 0 us | Second address accepted; RAR handshake done |
| 0.130 us | HP command flag rises while attention is zero |
| 0.760 us | Backend captures SEEK 0x3038; drive 0 abort is clear |
| 103.360 us | HP executes LIA on command channel; attention is still zero |
| 106.860 us | HP executes OTA on command channel with STATUS 000000 |
| 107.040 us | HP executes CLC on command channel |
| 107.180 us | HP executes STC,C on command channel for STATUS |
| 501.870 us | Worker reads 0x003C: STATUS opcode and drive 0 abort set; attention suppressed |

The nominal one-millisecond diagnostic delay takes approximately 103 us
at this CPU model's default divider. It must not be interpreted as a measured
one millisecond on the real HP. Raising the CPU divider independently of the
peripheral clock allows this relationship to be tested.

The diagnostic saves attention **before** requesting status, then checks
the saved word after status returns. A later attention update cannot repair
the saved zero. The original tape confirms `LIA CC` at 001013 followed by
`STA 000133` at 001014: the saved ATTN word is at **000133 octal**. The
STATUS call follows at 001021. This provides a direct front-panel check
after a real E21 halt; A at the common halt is the error-report value.

With 2000 us of extra capture delay, the first pending request is from startup.
The HP proceeds through four startup seeks and the failing step 2 seek while
that request remains pending. The backend eventually reads 0x003C rather
than any SEEK opcode. The single pending request bit does not queue those
commands. This recreates the hardware trace containing an unsupported request
without a newly dispatched SEEK.

## Reproduction

Prepare the source copy from the repository root:

```sh
python3 scripts/hp2116_seek_timing.py
```

Build with Verilator supporting SystemVerilog timing. The tested Docker
image is `verilator/verilator@sha256:a5b73e2fce0b2c483396f3800940f33b6faa802331a061c21694dd27b7352120`
(Verilator 5.052).

```sh
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD:$PWD" -w "$PWD/build/hp2116-seek-timing" \
  --entrypoint verilator \
  verilator/verilator@sha256:a5b73e2fce0b2c483396f3800940f33b6faa802331a061c21694dd27b7352120 \
  -Wno-fatal -Wno-UNUSEDSIGNAL --no-sched-zero-delay \
  --sv --timing --binary -j 2 \
  tb_hp2116.sv hp2116_cpu.sv hp12531c.sv hp12597a.sv \
  hp12566b.sv hp13210a.sv hp12539c.sv hp12845a.sv \
  --top-module tb_hp2116
```

Run the resulting executable in that directory, using the same container
mount if its runtime libraries require it:

```sh
./obj_dir/Vtb_hp2116 +DSN=151302 \
  +PTR_FILE=diagnostics/12960-16001_DSN151302_7900_01_CARTRIDGE_DISC.abin \
  +SEEK_US=500 +CAPTURE_US=0 +CPU_SCALE=1 +MAX_MS=1200
```

`CPU_SCALE` is the divider terminal count: 1 is the reference speed, 15 is
eight times slower. The requested divider takes effect at the diagnostic's
initial HLT 74 (P=012307), after configuration, so configurator UART input
still runs with the original timing. Panel-button pulses span a CPU sampling
edge at every supported divider.

`+COMPLETION_FLAG_ONLY=1` was a simulation-only experiment: SEEK address
acceptance requests backend service but does not raise the HP command flag.
The worker's attention write raises that flag on completion. ADDRESS RECORD
retains its immediate flag. That experiment did not edit the board RTL; the
current production RTL now implements the corrected completion timing.

`+STOP_AFTER_CYL1` stops when the diagnostic reaches its cylinder-1 seek in
step 21. Reaching that point establishes progress beyond step 2, not a full
diagnostic pass.

The testbench uses data/command select codes 22/23 octal; the physical board
uses 14/15. All four simulated drives start ready, matching the reference
worker convention. Disk images are never saved by this experiment. When
running concurrently, use separate `+LPTFILE` and `+PTPFILE` paths to keep
printer and punch output separate.

The earlier `baseline.log`, `late-capture.log`, and `slower-cpu.log` are
exploratory runs, not acceptance evidence: the old reference controller has
overlapping procedural FSMC bus assignments, and the initial slower-CPU run
changed speed during configuration and corrupted UART input. Use the
`core-*` results identified above.
