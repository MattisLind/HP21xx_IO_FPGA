# Step46 WRITE cylinder boundary

Physical retry after the READ-CLC FPGA fix passed step35, then halted:

```text
H45 WRITE IN STEP 46
E64 STATUS IS 000041 SHOULD BE 000000
H51 CYL 0000 HEAD 01 SECTOR 16 WORD COUNT 1024 UNIT 00
```

Step46 divides each track into thirds, writing the first, last, then middle
third. The final third on head1 starts at sector16: eight 128-word sectors
exactly consume the remainder of the cylinder. Source:
`build/reference/hp-diagnostics/12960-18005_Rev-1805.src`, lines142 onward.
000041 is End of Cylinder plus the aggregate error indication.

The STM32 backend incorrectly set EOC and completed immediately when its
buffer reached the cylinder's remaining byte count. The SV timing model did
the same and reproduces the physical E64/status000041. This is a backend
boundary error, independent of the step35 FPGA fix.

SIMH Release32 reaches P04302 (step47 entry) with error count000000 and
status000000, from the unpatched configured diagnostic at P2000/S0.
Evidence: `build/step46-investigation/simh/step46-console.log` and
`step46-debug.log`. SIMH's `hp2100_dp.c` tests data demand before checking EOC
at the next sector, rather than raising status after the last valid word.
The original Verilog WRITE worker similarly tests the EOC latch on the
following accepted word, before calling `calculate_rar` for that word.
Its implementation writes the extra word before checking; the production
fix instead discards that word to preserve bounds.

The correction adds a bounded WRITE/INITIALIZE boundary wait: no extra word
means successful completion; an extra request is consumed and discarded,
sets EOC, and completes without extending the media write. It uses the
existing20us response window. READ/CHECK are unchanged.

New native tests cover WRITE and INITIALIZE, both cylinder-ending heads,
last-sector and eight-sector exact fits, and one-word-past-boundary requests.
They verify status, write length, last valid data, consumed words and attention.
Old backend fails these tests; corrected backend passes the full native
ASan/UBSan suite (leak detection disabled because sandbox ptrace prevents
LeakSanitizer; address/undefined sanitizers remain enabled).

User is powering down the hardware. This investigation is offline; no
hardware programming was performed. Physical acceptance remains pending.
The step35 download bundle remains the previous installed release; do not
mistake it for corrected step46 firmware.

The corrected ARM build uses48296 flash bytes and22716 RAM bytes. Prepared
ELF/BIN/HEX and SHA256SUMS are under `build/step46-investigation/ready/`.
FPGA sources and bitstream are unchanged. The installed STM32 receipt is
preserved separately; the new firmware has not been programmed.

Corrected production-RTL CPU/SV timing-model runs pass through step46 at
200ns and8000ns backend polling. Evidence: `build/step46-investigation/cpu-results.json`.
These exercise the SV model; actual C++ firmware is covered independently
by the native sanitizer suite. SIMH comparison script now includes explicit
step46 coverage and passes steps34/35/46 and section1. Aggregate receipt:
`build/step46-investigation/result.json`. Full diagnostic/hardware success
is not claimed.

Complete next-session download package:
`build/step46-download/hp13210-step46-ready.zip`, unpacked `ready/` alongside it.
Includes new STM32 images, unchanged matching FPGA bitstream for power-up SRAM
reload, checksums, build/validation receipts and installation instructions.
See `build/step46-download/prepared.json` for verified archive/file hashes.
