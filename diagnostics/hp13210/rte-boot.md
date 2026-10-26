# RTE-II boot regression

Run the HP2116 CPU model with the production controller and the reference
RTE-II disk image:

```sh
python3 scripts/hp2116_rte_boot.py --run --out build/hp2116-rte-boot/final
```

This uses the locally installed Verilator Docker image, pinned by digest.
Docker access is required. Compilation and each run write separate logs in
the output directory. The two cases run concurrently, with 500 us and 4000 us
positioning delays. `acceptance.json` records input/generated source hashes,
runtime settings, log hashes and results.

Final validation on 2026-10-26 passed both cases:

| Seek delay | Boot/FMGR/DL/prompt | Simulated time at completion |
| --- | --- | --- |
| 500 us | PASS | 336.016 ms |
| 4000 us | PASS | 374.394 ms |

Each trace contains 17 SEEK and 30 READ requests, including 13 seeks whose
attention was suppressed by CLC. No WRITE requests occur in this workload.
Evidence is under `build/hp2116-rte-boot/final/`: `acceptance.json`, per-case
logs and extracted `*-console.txt` transcripts. Input, generated-source and
log hashes were verified after completion.

The script prepares a copy of the pinned reference testbench, substitutes
`fpga/hp13210/hp13210a_core.v`, and uses the backend model corrections from
`hp2116_seek_timing.py`. It copies `mh_boot.abs.new` and `RTE_MH.disc` from
the reference submodule. Disk changes exist only in simulated memory;
persistence is disabled. The reference submodule remains unchanged.

## Acceptance

A successful run must complete this console exchange:

1. Boot and print `SET TIME`.
2. Accept a blank time response and present the RTE command prompt.
3. Accept `ON,FMGR` and present FMGR's prompt.
4. Accept `DL`, print both `ILAB=SYS` and `ILAB=AUX`, each with a
   `NAME ... TYPE #BLKS/LU` directory header, and return to the FMGR prompt.

Only then does the model print:

```text
PASS: RTE-II boot, FMGR DL SYS/AUX directories, return to prompt
```

A console mismatch, unexpected CPU halt, or simulated time limit is a fatal
error. The Python runner also requires a successful process exit and the
PASS marker. RTE's raw high-bit console bytes are handled without assuming
the log is UTF-8. An intentionally short `+MAX_MS=1` run confirms that a
time limit fails rather than counting as a successful boot.

This covers a path that the seek-only diagnostic checks do not: RTE starts
a SEEK, issues CLC to suppress its attention, and submits READ before
positioning finishes. The backend model waits for that drive's positioning
worker before transferring data. Normal completed seeks also occur while
loading the bootstrap and resident system. These are CPU/DMA disk transfers,
not a test that injects a preloaded RTE memory snapshot.

## Limits and observations

The directory's numeric fields contain punctuation, such as `CR=;;;;:`.
Similar output is visible in the reference repository's
[`Booting RTE-II.png`](../../hp2116_verilog/Booting%20RTE-II.png).
The boot regression checks labels, headers and return to the prompt; it does
not establish correct numeric formatting, directory contents, or the cause
of that existing output problem.

Keep the reference console delays: 20 ms after `SET TIME` and 100 ms before
the FMGR and DL responses. An experiment capping all replies at 1 ms reached
`SET TIME` but received an unexpected `I` instead of the FMGR `:` prompt
after `ON,FMGR`, at both seek delays. Its logs are under
`build/hp2116-rte-boot/fast-reply-experiment/`; they are not acceptance runs.
The default runner preserves the reference delays. `--reply-us` is available
for explicit console timing experiments.

This exercises the Verilog controller with a SystemVerilog disk worker,
not the STM32 C++ binary, SD card, or physical HP interface. It is not a full
RTE filesystem or write test. No FPGA or STM32 programming is performed.
