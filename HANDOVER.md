# HP 2100 / HP13210 emulator: Codex handover

Updated **2026-10-29**, Europe/Stockholm. Read this first when continuing on the
laptop beside the HP 2100. This is a summary of the conversation and actual
bring-up state; some older README status paragraphs describe earlier stages.

## BOTH failed: preserved SWD/JTAG capture — 2026-10-30, latest

User explicitly requested inspection while both hung. NO reset, FPGA load, or
flash write. Xilinx dongle firmware initialized only. STM briefly halted for
register/dump capture, then resumed original HardFault loop.
Evidence build/startup-hang/20261030T215031Z/{result.json,swd.log,jtag.log,
sram.bin,ccm.bin,flash.bin,inspect.tcl}. Complete STM BIN matches installed
candidate. Same early HardFault: PC080094c8, CFSR1/HFSR40000000,
nested PCbe18cf86 (previous ba18cf86), outer PC08009630 in USB-init delay.
Media object unconstructed; SDIO all0. VTOR/vectors valid, BOR OFF.
FPGA IRcapture11, STAT0205: DONE0, INIT_B0, CRC_ERROR1, ID_ERROR0,
mode MasterSPI. This is a configuration CRC failure, not a controller LED fault.
Current ST-Link Vtarget3.276V is not a startup waveform measurement.
Both devices deliberately left in original failed states pending next step.
Common supply/reset problem remains hypothesis; need startup rail/reset captures.

## Widespread cold-start failures / power investigation — 2026-10-30

User reports most power cycles fail FPGA, STM32, or both; both starting is rare,
but normal operation works once started. Both use shared supply from HP; voltage
not yet confirmed. USB disconnected during latest tests, so USB backfeed is not
the explanation for those runs. Shared supply/reset timing is a hypothesis,
not established. Read-only ST-Link check (NO halt/reset/setting changes):
FLASH_OPTCR0x0fffaaed -> BOR_LEV0x0c = OB_BOR_OFF per ST HAL header;
RCC_CSR0x0e000000. Log build/sd-media-recovery/read-power-config.log.
Need confirm HP rail/input wiring, delayed reset experiment, scope local rails
and NRST/FPGA PROGRAM_B, INIT_B, DONE. No BOR option changes made.
AMD UG380 power-on precautions explicitly cover FPGA starting before SPI flash
is ready, including different regulator ramps from a common supply.

## Cold-start HardFault after SD recovery install — 2026-10-30, latest

User power cycle produced no STM32 CDC port (ST-Link still visible). Brief halt,
NO reset, captured full128KiB SRAM and registers in build/sd-media-recovery/.
CPU HardFault PC080094c8, MSP2001ff80; CFSR1 (IACCVIOL), HFSR40000000.
Nested frame PCba18cf86/xPSR8100000f, outer PC08009630 (delay reached via
USBD_LL_Init/CDC_init during premain). MediaRecovery object still zero/unconstructed;
SD retries had not started. Active VTOR08000000 and vectors valid. Entire installed
BIN verified against ready image. Exact cause of early fault NOT established.
Preserved cold-full-sram.bin, inspect-cold/fault/vectors.log, cold-fault-result.json.
Warm reset only (no reflash/FPGA changes) restored CDC and SD: attempts1/failures0,
all4READY, errors0. Status cold-fault-warm-reset-status.txt. USB opened briefly
then closed; HP serial untouched. MCU now running; user has not rerun diagnostics.
Do not claim software SD retries solve this separate early cold-start HardFault.

## SD recovery firmware INSTALLED — 2026-10-30, latest

User confirmed HP halted and explicitly requested programming. Full512KiB previous
STM32 flash backed up and verified by stm32_disk.py program; new ELF
b30734fe203fe91782d34b88a213d09d01356d73645f18d2570849ef1c2534a5
programmed, verified OK, reset/run. BIN74c4fab63a17a4fc396557e9a9033bdf25e86f4b2ee3d1d0aed29ba718ab34fc.
USB startup: SD mounted1, attempts1/failures0/removals0; all4READY;
commands/errors/trace_dropped0. Boot traces N0..N3 then SD/CF/R0..R3 confirm
initial offline-to-ready publication. STM32 USB opened briefly for status and
closed afterward; HP serial port untouched. No FPGA access or SPI changes.
Receipts build/stm32-disk/programmed.json and build/sd-media-recovery/installed.json;
startup transcript build/sd-media-recovery/installed-startup-status.txt.
Candidate tests below passed before install. Cold power-cycle and physical card
removal/reinsertion acceptance are still PENDING; no HP diagnostic on new firmware yet.

## SD recovery candidate preparation — 2026-10-30 (subsequently installed above)

User approved startup retries and software-only card removal/reinsertion recovery.
Serial ports were explicitly disconnected before the latest power cycle and stay
closed until requested; user reports that latest power cycle worked.
No STM32 schematic was present in this checkout; original DevEBox schematic
retrieved via the existing board reference and saved under
build/reference/stm32-board/DevEBox-STM32F4XX-M.pdf. U5 contact9 SD_NC is not routed
to MCU GPIO. Contact2 CD/DAT3 is PC11 SD data, not mechanical card detection.
Candidate adds idle-only SD status probes, startup delay and retry backoff,
FAT/SD teardown with stale FIL objects abandoned, config/image reopen on insertion,
and bounded post-transfer waits via local adapted sd_diskio.c. Installed firmware
and SPI image are untouched. See firmware/stm32-disk/README.md for timing/limits.
Original build artifacts preserved under build/sd-media-recovery/before-build/;
installed known-good 4MHz artifacts still build/step47-investigation/sdio4-ready/.
Final ARM build and ASan/UBSan backend/recovery/SD-driver tests PASS.
Ready artifacts build/sd-media-recovery/ready/; result.json records hashes.
Build uses PATH to build/stm32-tools/python/cmake/data/bin and PYTHON=
build/stm32-tools/python-runtime/cpython-3.12.15-linux-x86_64-gnu/bin/python3.
No hardware testing of recovery yet. Never remove media during HP writes as a
routine test; use stopped HP and disposable images for reinsertion acceptance.

## Cold-power diagnostic E50 — 2026-10-30, later update

User power-cycled, then reported E50 UNIT0 MISSING-PRESENT NONE twice.
This cold boot SUCCEEDED for FPGA: read-only JTAG STAT373c, DONE high, without
FPGA reload, reset, or flash write. Xilinx dongle RAM firmware alone initialized.
STM32 USB reports SD/FAT mount failed, E11, all4OFFLINE, commands/errors0.
Firmware setup calls images.mount() once; no automatic retry. Reset STM32 only
while HP halted at E50: FAT mounted, all4READY, commands/errors/dropped0.
FPGA remained untouched throughout. This establishes a cold-start SD mount
problem; readiness/power timing is plausible but exact cause unproven.
Evidence build/spi-mailboxes/cold-boot-result.json and cold-sd-retry-status.txt.
Current STM32 running/all4READY; restart diagnostic P002000/S000000 when ready.
Earlier failed boot attempts below remain historical; this new cold boot passed.

## Current hardware — 2026-10-30 SPI installation

Latest mailbox controller b19233751b4501c24df062d1f8ee6b5ee5a651f0ed7983794017609db39d1810
is now programmed in SPI flash and independently verified. Full pre-write 2 MiB
backup and verification logs: build/spi-mailboxes/install-20261030T191239Z/.
The complete controller flash payload also matched byte for byte after power cycling.
Standard xc3sprog -R (IPROG) left DONE low, STAT1204, FSMCFFFF. User cold power
cycle also produced no LED heartbeat. Original blink rebuilt and passed SRAM
(user confirmed blinking); its verified flash image failed standard -R too.
Direct JPROGRAM reset succeeded for blink and subsequently for the restored latest
controller flash image: STAT373c, DONE high, scratch/attention FSMC checks PASS.
Temporary utility source/binary: build/spi-mailboxes/jprogram-status{.cpp,}; -c xpc -R
uses JPROGRAM, NOT the standard IPROG sequence. No production programmer changes.
Cold power-on failure remains unexplained and has NOT been retested after this.

Controller was booted clean again via JPROGRAM and STM32 reset/run. FAT mounted,
all four drives READY, commands/errors/dropped0, CSR/request/command/RAR0,
last_error none, verified through USB status twice. STM32 firmware unchanged.
Serial capture PID7969 reconnects both ports; logs build/serial-logs/20261030T191053Z/.
HP FTDI AH01E1EM at2400/7E2; STM32 CDC at115200/8N1. Xilinx RAM cable firmware
initialized after reconnect with Linux fxload -t fx2 -D <discovered USB node> -I
build/firmware/xusb_emb.hex. Reidentify USB nodes each time.
Receipt build/spi-mailboxes/controller-installed.json. HP diagnostic rerun started at P002000/S000000 with data14/command15.
Captured LONG PASS0001, heads0/1, unit00, 0000errors. User subsequently
reported stopped. No second PASS or HP error captured. Final USB status: all4READY,
commands68299, backend errors4, last_errorE06 (cylinder mismatch),
trace_dropped310302 (E99 trace overflow), READmax6us/WRITEmax13us.
These backend counters do not replace the HP diagnostic verdict. Final transcripts
under build/spi-mailboxes/diagnostic-final-*.txt; neither board reset afterward. Keep cold boot issue separate
from diagnostic acceptance. STM32 is RUNNING, not halted.

## Current hardware and capture — 2026-10-29

### Experimental mailbox FPGA PASSED; code review completed

Current branch fpga-rework-experimental, commit32ed30c ("Experimental also
works"). Saved HP log contains LONG PASS0001 and0002, both0000errors, unit00
heads0/1; user confirmed this version worked. Installed FPGA/STM32 images are
unchanged from the setup below. Do not infer the current HP RUN state from this
review: only saved logs were read, with no hardware access.

Fresh review: diagnostics/hp13210/code-review.md. No production RTL/firmware
changes or programming. Main tuning finding: bool(Serial) calls delay(10) on
every idle loop; Serial.dtr() has identical DTR semantics without the delay,
confirmed against installed ELF and isolated loop tests. Safe cleanup candidates
include redundant read_wait_ state and unused RTL. Actual RTL tests reproduce
unselected IOO clearing attention and CRS sticking the first-word seek ack.
Native model reproduces pending-slot seek loss; joined C++/RTL validation is
still needed. Pinned SD driver also has unbounded post-transfer ready waits.
Evidence/isolated candidates under build/code-review/. None is installed.

### Experimental mailbox installation record

Branch fpga-rework-experimental, commit7d59ce5. User authorized programming
and another normal diagnostic. Installed SRAM FPGA
b19233751b4501c24df062d1f8ee6b5ee5a651f0ed7983794017609db39d1810
from build/queue-review/ready/controller-mailboxes.bit. STM32 existing4MHz SDIO
BIN verified before and after; no rewrite needed, ELF remains f006ce15... .
STM halted/load/FSMC scratch+attention checks/reload clean/BINverify/reset/run
PASS. FAT mounted/all4READY, commands/errors/dropped0, CSR/request0. NoSPIwrites.
Serial capture5994 and temporary sleep/idle inhibitors34596/38734 active.
User subsequently ran P002000/S000000; acceptance recorded above.
Receipt build/queue-review/installed.json and experimental-*.log/status files.

IMPORTANT: this candidate is UNINSTRUMENTED, four-bit FSMC address decode.
Do NOT use old counter/target/loss-recorder/sdio4 trace scripts or high debug
bank accesses. On failure first preserve console and dump backend/full MCU
SRAM only using build/queue-review/capture-experimental-failure.tcl; save stdout
experimental-run-capture.log. It halts STM32 and leaves it halted, no FSMC reads.
Original stable f3be9b... recorder bit retained under
build/step47-investigation/address-qualified-ready/controller.bit for rollback.

### Experimental per-drive request slots; prior software-only validation

User committed stable result as d6b9a8d and tagged `working`. HP log confirms
LONG PASS0001..0004, each0000errors, unit00 heads0/1; user then requested an
orderly stop with S100000. HLT102004 at001433, P001434, A100000 matches ENDST.
Stable loaded FPGA remains f3be9b... and STM32 ELF f006ce15... (4MHz SDIO).
No hardware access or programming during this request-capture experiment.

Active software branch fpga-rework-experimental replaces the8-entry FIFO
with one SEEK destination per drive plus one ordinary-command slot. No head,
tail, occupancy, or FIFO overflow. Busy-SEEK sets SeekCheck without replacing
original destination. CLC/CRS drop an unconsumed ordinary command; accepted
seeks survive and retain live attention suppression. CSR latches selected
packet plus returned IRQ bits atomically at read START, avoiding CLC/new-arrival
races during the read. Same STM32 register sequence, no firmware changes.
See diagnostics/hp13210/seek-mailboxes.md. RTL/TB/docs retained on the experimental branch.

All22 controller timing variants PASS including new race/abort/multi-drive
tests. Final board/LED build, all eight CPU seek/read replays and both RTE-II boot/FMGR
regressions PASS. Final bitstream b19233751b4501c24df062d1f8ee6b5ee5a651f0ed7983794017609db39d1810,
minimumperiod7.435ns, zero timingerrors. Mapped resources baseline->candidate:
392->395registers,449->453LUTs,191->190occupiedslices,32->24memoryLUTs.
No significant area reduction; architecture no longer has a command FIFO.
Package build/queue-review/seek-mailboxes-ready.zip; experiment.json records
source hashes/results. Candidate subsequently downloaded and passed as detailed
above. Artifacts build/queue-review/;
ISE baseline build/queue-baseline-board, final build/queue-mailboxes-v3-board.
Do not program anything based on old handover pending-run entries below.


### 4MHz SDIO firmware INSTALLED; fresh diagnostic requested

New STM32 ELF f006ce156f847832dc0579f44e8468944e20016752aeaf51f87d0a97e11aae8e
installed, verified, reset/run; backup512KiB verified via stm32_disk.py program.
Prepared ELF/BIN/receipts build/step47-investigation/sdio4-ready/. New firmware
sets SD_CLK_DIV=10U (4MHz) for polling SDIO FIFO margin; native ASan/UBSan tests
PASS. Actual SDIO CLKCR0000090A verified. IMPORTANT: old step46 readyBIN is now
obsolete for verification/reload; use sdio4-ready/disk_backend.bin. No SPIwrites.

Same fixed recorder FPGA f3be9b71740e1f1851f6a9fb34d0bb1db6415d057645c5517d6a1426f3053033
reloaded intoSRAM, FSMC PASS, reloaded clean, newSTM BIN verify/reset/run PASS.
FAT mounted/all4READY, commands/errors/dropped0, CSR/request0. User asked for
fresh P002000/S000000 RUN, halt at failure and Done; result PENDING.
Captures20261029T062605Z and temporary inhibitors34596/38734 remain active.
AfterDone copy read-address-qualified-trace.tcl, change output backend filename
to sdio4-run-backend-sram.bin, save stdout sdio4-run-trace.log. Use WITHOUT RESET.
Preserve latest HP text, SRAM and HAL SD error if any; script leaves STM halted.

### Address glitch fixed physically; prior SD write underrun at cylinder66

Latest Done: step46 WRITE E64 STATUS004103 expected000000, CYL0066 HEAD01
SECTOR16 WORDCOUNT1024 UNIT0. Earlier short-READ failure cleared: retained
READ commits/events/HPinputs1024, histogram DATA4=1024, F=0. Frozen stateC085
captures ignored NADV glitch. Backend reached8111commands, errors4; last_error
E08 WriteError, failed/online drive0=1/0. SD HAL error0x10=TX FIFO underrun;
FIL.err0, fptr1634304. SD default24MHz polling driver sharesCPU with interrupts.
Evidence address-qualified-run-{trace.log,trace.csv,hp.txt,backend-sram.bin},
cyl66-full-sram.bin, storage-layout.txt, cyl66-state.log.

SRAM-only targeted SD test changed CLKCR divider10 to4MHz, preserved original
2048bytes at fileoffset1632256, rewrote identical bytes1024times withsync and
readback verification. PASS1024, stage/error0, CLKCR90A, HALerror0. Full SRAM
backup before-sd-stress-sram.bin. STM32 currently HALTED at RAM test BKPT.
FPGA f3be9b... retained. Firmware CMake SD_CLK_DIV=10U built/programmed/verified; native backendtests PASS.
All later setup described in latest section above.
Captures and temporary sleep/idle inhibitors remain active.

### Address-phase fix installed; prior manual request completed

SRAM FPGAf3be9b71740e1f1851f6a9fb34d0bb1db6415d057645c5517d6a1426f3053033
installed from build/step47-instrumented-board/controller.bit; snapshot
build/step47-investigation/address-qualified-ready/. Production and recorder
22variants PASS; board/LED and passive histogram/trigger tests PASS. Both
originalCPU step47 replays pass (scale9/poll200ns, scale19/poll8000ns).
ISE minimumperiod9.622ns, zeroerrors. FPGA stable address qualification now
protects both address latch and write active/done rearm from single-sample NADV
low glitches. Earlier read and write qualifiers retained.

Halt/load/FSMC/8192 jittered RAM DATA write+CSRpoll+mirror reads PASS, zeroerrors,
commits8192/events8192; FPGA reloaded clean, unchanged BIN flashverify/reset/run
PASS. No SPI/STM32 flashwrites. Awaiting user P002000/S000000 RUN, halt at error,
replyDone. Both captures and temporary inhibitors remain active.
After Done run OpenOCD -f build/step47-investigation/read-address-qualified-trace.tcl
WITHOUT RESET, save stdout address-qualified-run-trace.log. It saves
address-qualified-run-backend-sram.bin; leaves STM32 halted. Same bank and
histogram interface as loss recorder below. Raw NADV glitch trigger retained,
so a frozen trace can now be an ignored glitch; histogram/console determine
whether words are lost. Complete physical diagnostic acceptance PENDING.

### Captured missing writes EXACTLY; prior failed run evidence

Latest Done: step47 E13 **0954/1024**, E64 STATUS000041 versus000000,
CYL0 HEAD1 SECTOR16 UNIT0. Counters954 DATA commits/events/HPinputs;
C++ position/length2048/2048bytes. Histogram DATA4=954, F=70: all70 missing
software writes redirected to addressF. Frozen stateC044. Trace at trigger0:
AD transitions4->FFFF while NADV/NOE pulse low20ns with NWE low. Raw address
latch overwrites address4 withF; write_active resets/restarts atF. This accounts
exactly for1024-954. Evidence loss-recorder-run-{trace.log,trace.csv,hp.txt,
backend-sram.bin}. STM32 currently HALTED; HP halted; ae2d81... still installed.

Production and recorder now require stable address phase over two50MHz samples
before latching AD or clearing write active/done. Captured NADV+NOE20ns pulse
added to permanent controller test: old core FAILS, fixed production22variants
PASS. Board and directed passive histogram/trigger tests PASS. Full instrumented
regression, originalCPU step47 replays, and ISE build PASS (see latest section).
Read and write qualifiers from earlier fixes retained. New qualified image installed as detailed above.

### Loss recorder installed; previous manual request completed

SRAM image ae2d81cde72ddb34f4770935e35999d3ef304b1d60a9274741da22242314299e
installed from build/step47-instrumented-board/controller.bit; snapshot
build/step47-investigation/loss-recorder-ready/. Timing10.071ns, zeroerrors.
Full22 variants, board/LED, mirror/trace tests and directed histogram/both
loss-trigger tests PASS. Protocol same as read-qualified9ba36674...; only
passive recorder changes. Halt/load/FSMC/reload/BINverify/reset/run PASS.
Next user run P002000/S000000 RUN, halt at failure, replyDone.
After Done use OpenOCD -f build/step47-investigation/read-loss-trace.tcl,
save stdout loss-recorder-run-trace.log. No reset; script leaves STM32 halted.
It saves loss-recorder-run-backend-sram.bin and dumps per-register histograms.
Debug bank same as targeted recorder except mirror at CPU60000030 returns
write_histogram[scratch&15] when scratch bit8 set; scratch100..10F selects.
Trigger on unexpected writeaddress (except DATA4/ATTN6/SET8/CLRA) or unfinished
write at next NADV address phase in cylinder0/head1/sector16 READ. Previous
old-flag-high trigger retained. Decoder decode-target-trace.py accepts logpath
and writes CSV; traceHP lowbits match read-qualified description below.
Both captures and temporary sleep/idle inhibitors remain active.

### Qualified-read rerun STILL fails; preserved evidence

Latest Done: step47 E13 **0935/1024**, E64 STATUS000041 versus000000,
CYL0 HEAD1 SECTOR16 UNIT0. Counters935 DATA commits/events/HPinputs;
C++ position/length2048/2048bytes. Recorder state0032, NO_FROZEN_TARGET_TRACE:
the earlier DATA-commit/old-flag-high fault did not recur, but89 software words
have no decoded FPGA DATA commit. Evidence read-qualified-run-trace.log and
read-qualified-run-backend-sram.bin under build/step47-investigation.
STM32 left HALTED, HP halted. Current installed9ba36674... unchanged.
Passive recorder triggers for unexpected write address and an
uncommitted write at next NADV address phase, plus per-register write histogram
are now installed (see latest section).
Production protocol unchanged during this instrumentation step.

### Qualified-read fix installed; previous manual request completed

Installed SRAM FPGA9ba36674dc4c90ab124a5bc94cfc92a26f0cb374c83a12ee1259ec00d77e85c0
from build/step47-instrumented-board/controller.bit; snapshot read-qualified-ready/.
ISE minimum period7.238ns, zero timingerrors. Production+recorder full22variants,
board/LED, recorder mirror/counter/trace test PASS. Original CPU isolatedstep47
replays CPUscale9/poll200ns and CPUscale19/poll8000ns both PASS.
STM32 halted/load/FSMC PASS/reload/unchanged BIN flashverify/reset/run complete.
FAT mounted, all4READY, commands/errors/dropped0, CSR/request0000. No flashwrites.
User asked for P002000/S000000 RUN, halt at failure, replyDone; result PENDING.

Last target run: step47 E13 **0944/1024**, E64 STATUS000041 versus000000,
CYL0 HEAD1 SECTOR16 UNIT0. DATA commits944, events944, HP inputs944 while
C++ position/length2048/2048 bytes. Evidence target-run-trace.log,
target-run-waveform.csv, target-run-backend-sram.bin under step47-investigation.
Waveform shows NOE low20ns while NWE low during DATA write, false read-DATA
ack clears IRQ/sets flag buffer380ns before real completion; HP flag rises340ns
early. Permanent overlap regression FAILS old core, PASSES fixed core.
Production and recorder now require NWE high and two read-window samples before
read side effects; bus output release remains immediate. Physical acceptance pending.

After Done, use read-target-trace.tcl WITHOUT RESET, but copy it first to replace
output target-run-backend-sram.bin with read-qualified-run-backend-sram.bin;
retain stdout in read-qualified-run-trace.log so prior evidence stays intact.
Script halts STM32 and leaves it HALTED. Do NOT use old read-counters.tcl bank.
TraceHP lowbits3:0 are now readDATAnegedge, readValid, rawReadWindow,0;
upper12bits unchanged. Scopebank/trigger described in historical section below.
Serial captures20261029T062605Z and temporary inhibitors34596/38734 active.

### Fresh run STILL fails step47; TARGETED recorder installed, retry pending

Fresh H0 captured with USB stable: H46 READ IN STEP47; E13 0966/1024,
E64 STATUS000041 expected000000, CYL0 HEAD1 SECTOR16 UNIT0. Normal passive
counters966 staged/HPinputs/dataSTC; flagbusy36, CLF0, IRQfull0, rawSTC967.
C++ SRAM position/length2048/2048 bytes. Evidence `fresh-retest/` and
`fresh-run-physical-counters.log`/`fresh-run-backend-sram.*` under step47-investigation.
The captured address/data fault is real and its standalone tests pass, but
stable-release fix is NOT a complete disk diagnostic solution.

Installed targeted recorder FPGA809a8bbe8740d9c3cd424efe58e48f67a23c01a674e72f8b27170104d9854089
in SRAM (7.595ns). SAME stable-release protocol logic; passive per-READ global
DATA commit/event counters and256-sample AD/control/HP flag recorder added.
Trigger: cylinder0/head1/sector16 READ completion while old data flag high.
All22 variants +mirror/counter/trace unit test PASS. STM32 halt/load/FSMC/reload,
unchanged BIN verified/reset/run, all4READY/idle zero counters. No flash writes.

User asked for P2000/S0 RUN once more; reply pending. After Done, use
`build/step47-investigation/read-target-trace.tcl` (NOT read-counters.tcl!)
via OpenOCD WITHOUT RESET. It halts STM32, reads counts +frozen256-sample
waveform and saves backend SRAM, leaving STM32 HALTED. Scopebank CPU20state,
24commits,28events,2CHPinputs,30DATA mirror,34traceHP,38traceAD,3Ctracecontrols;
all CPU addresses based60000000. Scratch1C selects trace index0..255.
State bits15triggered/14done/7:0nextpointer; 16 post-trigger samples plus
trigger+final stop cycle, chronological trigger offset238 of256 samples.
Tracecontrols15:12=IOI,dsel,STC,CLF;11:8writeaddress;7:0=NE,NADV,NWE,NOE,
writewindow,active,NWEhigh-delayed,done. TraceHP15:4=dataFF,dataFBF,dataIRQ,
commandFF,readEnded,ENF,readCSR,writeDATA,writeDATAnegedge,writeAttention,
readCSRnegedge,STCnegedge;3:0zero. Target source snapshot targeted-recorder-core.v.

Both serial captures remain active20261029T062605Z; sleep/lid inhibitor34596
(child34597), GNOME idle inhibitor38734 active TEMPORARILY. Clean up those
processes when diagnostic session ends. Older state paragraphs below historical.

### USB restored; FRESH fixed-image diagnostic ready, user retry pending

USB loss was laptop LID-CLOSE suspend: logind08:38:54 lid closed/suspending,
08:39:06 lid opened, kernel08:39:07 hub2-2 and children disconnected onresume.
User reinserted upstream USB lead; all4 devices returned, Xilinx stillwarm0008,
both captures automatically reconnected. Temporary systemd inhibitor PID34596
(child sleep34597) blocks sleep/idle/lid; GNOME idle inhibitor also active to
prevent screen blanking. These are temporary processes, no permanentsettings;
remove when diagnostic session ends. Kernel/logind evidence under
`build/step47-investigation/usb-suspend-*.log`.

Retained final-fix run counters955 DATA events/HPinputs/dataSTC, flagbusy37;
C++ SRAM2048/2048 bytes. Latest HP console text was LOST during USB outage.
User reports A=64 B=4 M012135 HLT102001. This is NOT a diagnostic pass.
Fast SRAM-only tests (no flash changes) subsequently passed8192 scratch,
8192 jittered scratch, and8192 jittered DATA/mirror tests; DATA global commits
and completion events both8192. Temporary DATA-scope image used only for these
measurements, not the next diagnostic; its bank differs from normal counters.

User requested a fresh diagnostic rather than digging further into the lost
capture. Restored EXACT fixed+counter image9e623d70... from
`build/step47-investigation/ready/controller-instrumented.bit`, STM32 halted,
FSMC checks PASS/reloaded, unchanged STM32 BIN verified/reset/run. No flash
writes. Fresh FAT/all4READY, commands/errors/dropped0, CSR/request0000.
Both ports active in20261029T062605Z. User asked to run P2000/S0, RUN, leave
HP halted at failure, replyDone. Pending. Read normal passive counters WITHOUT
RESET after reply usingread-counters.tcl. DO NOT load current
`build/step47-instrumented-board/controller.bit` blindly: it is the temporary
DATA-scope image; the verified ready/ image is the actual restored one.

### USB hub disconnected — final fixed-image diagnostic result NOT captured

Latest user replied Done to the fixed-image retry request. No new H0 or disk
commands were captured after final fixed image installation; latest visible
console failure remains historical guard-image step26/E47. Both serial ports
disconnected2026-10-29T07:39:06Z (08:39 Stockholm). Fresh host lsusb/by-id shows
HP FTDI, STM32 CDC, ST-Link and Xilinx cable all absent. Monitor PID5994 is
alive, waiting to reconnect. Do NOT claim final fixed image passed/failed disk
diagnostics. Its halted8192-transaction scratch stress passed0 errors.

User asked to reconnect hub, keep HP halted, and report whether FPGA/HP power
was interrupted. Reply pending. If FPGA stayed powered, preserve/read counters
WITHOUT RESET first. If FPGA lost power, SRAM image lost: reload fixed image
via normal halt/FSMC/reload/STM verify-reset flow once HP halt is established.
Production fixed503f63a2... and instrumented fixed9e623d70... both available in
verified `build/step47-investigation/hp13210-fsmc-stable-release-ready.zip`.
Current hardware power state unknown; previous all4READY status is historical.
One combined live status/query tool attempt timed out in automatic approval
review; subsequent read-only host checks succeeded and established disconnect.
No hardware changes in this check. Latest result receipt updated accordingly.

### FSMC address/data release fault captured; stable-release fix INSTALLED

Latest guarded run stopped earlier at step26/E47: word35=000004 instead of
137752, but FPGA/HP both128 words. Scratch stress reproduced address000E
substitution (3/512); two-sample write-window candidate failed65/8192 and was
rejected. On-FPGA waveform recorder captured NWE high for one20ns sample at
address/data transition, while AD changes000E->F77F, followed by real data
NWE-low phase. Old core commits address then data; write-once guard keptaddress.

Production core now waits for NWE high on TWO consecutive samples, retaining
pending write/last data across brief releases; one commit per NADV transaction.
Permanent tests replay measured pulse, reject old core, all22 variants and
board/LED PASS. Installed FIXED+counter image9e623d70... SRAM, ISE8.088ns;
FSMC checks/reload, STM32 BIN flash verify/reset PASS. No STM32 or SPI flash
writes. Halted scratch stress8192/8192 PASS (previous65 failures). Both CPU/SV
step47 replay cases PASS (50MHz FPGA, CPU9/poll200ns; CPU19/poll8us).

All4READY/FAT, commands/errors/dropped0, CSR/request0000 after stress/resume.
Both captures active20261029T062605Z. User asked to run P2000/S0 again and
leave HP halted. Next read console +passive counters via read-counters.tcl,
without resetting; current debug bank is again eight counters, not trace RAM.
Physical diagnostic acceptance pending. Production bitstream503f63a2...
(7.213ns) built/validated, NOT installed; instrumented fixed bitstream remains
installed. Verified ready ZIP: `build/step47-investigation/hp13210-fsmc-stable-release-ready.zip`,
receipt `prepared.json`. Package distinguishes production vs installed counter image. See updated
`diagnostics/hp13210/read-cylinder-boundary.md`, `build/step47-investigation/result.json`
and waveform/stress evidence. Older candidate paragraphs below are historical.

### Step47 counter evidence; write-once FPGA candidate INSTALLED, retry pending

Counter rerun: E13 0936/1024, status000041. FPGA counted1179 DATA completion
events but936 HP inputs and936 accepted data STC. Flag-busy177, CLF overlap0,
IRQ-full0, rawSTC937. C++ SWD SRAM snapshot confirms2048/2048 byte transfer
position/length (1024 logical stages), head1/sector16. Evidence under
`build/step47-investigation/physical-counters.log` and `backend-sram.*`.

Directed test: repeated NWE excursions within one NADV address transaction
produce duplicate DATA events in baseline. Candidate write-done latch permits
one commit until next NADV. Physical cause/fix still unproven; waveforms not
captured. Candidate remains isolated under `build/step47-instrumented-board/`;
production core unchanged. All22 variants +board/LED PASS, ISE7.130ns.

Loaded guarded counter FPGA55b65dc8... SRAM with STM32 halted; FSMC PASS,
reloaded, existing STM32 BIN verified at08000000, reset/run. Initial ELF verify
attempts failed before restart; final BIN flash verification explicitly PASS.
No STM32 flash write or SPI flash write. All4READY/FAT, commands/errors/dropped0,
CSR/request0000. Captures active20261029T062605Z. User asked for P2000/S0 rerun,
leave HP halted, reply Done. Next read passive counters without reset using
`build/step47-investigation/read-counters.tcl`; compare staged events to1024,
HP inputs/data STC and console word count. Full receipt `result.json` nearby.

### Step47 investigation — temporary passive-counter FPGA installed

SIMH32 passes first step47 pattern/cylinder: six1024-word READs, status0,
errorcount0. Original unmodified READ worker with production transport passes
at CPU divider1; divider3 times out. Literal original-model replay has not
passed; historical d855d26 reports a long pass before CPU scaling was added
in06c060d. No proven physical root cause or functional fix yet. See
`diagnostics/hp13210/read-cylinder-boundary.md` for scope and limitations.

Installed temporary FPGA SRAM image `build/step47-instrumented-board/controller.bit`
adds passive counters only; production RTL files unchanged. All22 variants,
board/LED and counter-side-effect tests PASS; ISE6.886ns. STM32 halted for
load/FSMC/reload, then existing17f81beb... ELF verified/reset/run without flash
write. SPI flash untouched. FAT/all4READY, commands/errors/dropped0, idle
CSR/request0000. Both captures remain active in20261029T062605Z.

User asked to rerun P002000/S000000 and leave HP halted. After failure, collect
fresh USB status, then halt STM32 WITHOUT RESET and run
`build/step47-investigation/read-counters.tcl` via OpenOCD. Debug registers
CPU0x60000020..3C stride4: staged,HPinputs,dataSTC,flagBusy,flagCLF,irqFull,
rawSTC,lastFlags. Retained across status commands, cleared on new READ/CHECK
or reset. This will distinguish excess requests from lost ready flags.
Receipt `build/step47-investigation/result.json`. Physical rerun pending.

### Physical retry: step46 PASSED; new halt at step47 READ

Fresh H0 banner followed by H46 READ IN STEP47, E13 0953 WORDS TRANSFERRED
1024 EXPECTED, E64 STATUS IS000041 SHOULD BE000000; H51 CYL0000 HEAD01
SECTOR16 WORD COUNT1024 UNIT00. This provides physical evidence that the
step46 WRITE correction passed; full diagnostic still fails. Final STM32 trace
RD/EC/CM. Fresh status: all4READY, commands71/errors3/dropped0, CSR0040,
request00C0, command2000, RAR0030, last_errorE06, READmax6us/WRITEmax3us.
Evidence `build/step46-download/install/retest/`. Both captures remain active.
No hardware changes or HP inputs during this check. Step47 cause uninvestigated.

### Step46 FPGA/STM32 INSTALLED — ready for diagnostic retry

User confirmed HP halted. Both serial ports captured under
`build/serial-logs/20261029T062605Z/` (HP FTDI AH01E1EM at2400/7E2;
STM32 CDC378035813433). Xilinx cable RAM firmware initialized; JTAG
XC6SLX9 ID24001093 detected. Verified package checksums and STM32 source/build
fingerprints. STM32 halted, FPGA SRAM loaded with1c7f3790..., FSMC scratch
and attention checks PASS, same FPGA reloaded to clear test state.
SPI flash untouched. New STM3217f81beba4dc... programmed/verified/reset via
repository flow after fresh verified512KiB backup; see
`build/stm32-disk/programmed.json`. Initial SD/FAT mount failure cleared after
program/reset without card changes: two fresh reports FAT mounted, all4READY,
commands/errors/dropped0, CSR/request0000, last_error none.
Installation receipt `build/step46-download/install/installed.json`.
No HP console input sent. Physical step46 acceptance remains PENDING.
Keep FPGA powered. Reload diagnostic if HP memory lost; configured normal
restart P002000/S000000, data14/command15 octal.

## Current hardware and capture — 2026-10-28

### Step46 DOWNLOAD PACKAGE READY for reconnection tomorrow

User requested firmware/bitstream ready for next dongle connection. Complete
verified archive: build/step46-download/hp13210-step46-ready.zip; unpacked:
build/step46-download/ready/. Prepared receipt: build/step46-download/prepared.json.
Contains NEW STM32 ELF/BIN/HEX17f81beb... and matching FPGA controller.bit
1c7f3790...; FPGA rebuild unnecessary because sources/build fingerprints match.
FPGA bitfile is needed again after power loss (volatile SRAM). Both source/build
receipts, checksums, ZIP integrity and archived file digests verified. No hardware
access or programming in this preparation. Step46 physical acceptance pending.

Follow the package README for reconnection, cable firmware, capture, STM32 halt,
FPGA SRAM load/FSMC/reload, then repository STM32 program with fresh verified
512KiB backup, image verification/reset and FAT/all4 READY/idle checks. Unlike
step35, STM32 must be updated: new ELF differs from installed5c509335....
SPI flash remains untouched. HP diagnostic must be reloaded if power lost its
memory. This package supersedes step35 for tomorrow's retry.


### Step46 root cause and STM32 correction — OFFLINE, NOT programmed

User is powering down HP/dongles; continue offline. Step46 writes each track
in thirds (0–7,16–23,8–15). Head1/sector16 +1024 words exactly fits the
cylinder. STM32 incorrectly raised EOC at the last valid word (status000041),
instead of waiting for demand beyond the boundary. Existing CPU/SV model
reproduces the same physical E64. SIMH32 passes step46, six1024-word writes,
status000000/errorcount0; original Verilog WRITE worker also delays its EOC
check until the next accepted word (source comparison).

Production STM32 now waits at the full-buffer boundary: no extra word within
normal20us window means success; extra word is consumed/discarded, reports
EOC and completes without writing beyond the cylinder. Applies WRITE/INIT;
READ/CHECK and FPGA RTL unchanged. Sixteen new native boundary cases reject
the old backend. Full ASan/UBSan native suite PASS (LSan disabled for sandbox
ptrace). ARM build PASS:48296 flash/22716 RAM bytes. New ELF SHA256:
17f81beba4dcfa37837fd5014d92d12cd1628d818e4c727e8d30724d47b66df1.
Prepared STM32 ELF/BIN/HEX +checksums in build/step46-investigation/ready/.
NOT programmed. Existing build/stm32-disk/programmed.json remains historical
actual last installed5c509335...; success.json is the new prepared build.
Corrected CPU/SV timing model passes through step46 at200ns/8000ns polling.
SIMH comparison steps34/35/46 and section1 PASS. Aggregate evidence receipt:
build/step46-investigation/result.json.
Step35 zip remains the previous release, not corrected step46 firmware.
FPGA SRAM is volatile: reload step35 FPGA after power loss; HP diagnostic
memory also needs reloading after HP power loss. Use backup/verify firmware
programming procedure when hardware is connected and HP halted.

Evidence and details: diagnostics/hp13210/write-cylinder-boundary.md and
build/step46-investigation/. Physical retry still required. No new hardware
programming during this investigation.


### Physical retry: step35 PASSED; new halt at step46 WRITE

Fresh H0 banner after SRAM installation; diagnostic advances beyond step35
and halts H45 WRITE IN STEP46, E64 STATUS IS000041 SHOULD BE000000;
H51 CYL0000 HEAD01 SECTOR16 WORD COUNT1024 UNIT00. Physical evidence now
supports the READ-CLC step35 fix. Full diagnostic still does not pass.
Fresh STM32 query: all4 READY, commands53/errors3/dropped0, CSR0040,
request00C0, command1000, RAR0030, last_errorE06; READmax6us/WRITEmax3us.
Preserved evidence: build/step35-download/install/retest/result.json,
hp.txt and stm32-status.txt; serial capture remains active. No hardware
changes during this check. Step46 cause has not yet been investigated.


### Step35 FPGA INSTALLED — ready for physical retry

HP halt confirmed by user. Initialized Xilinx cable; loaded production READ-CLC
fix into XC6SLX9 SRAM (SHA256 1c7f3790170f5b56724b706f539eac732951aac8b27703935d741f8b40f02b46).
STM32 halted during loading; FSMC scratch/attention checks PASS, then FPGA
reloaded to clear test state. Existing STM32 ELF5c509335... verified over SWD
and reset/run; no STM32 flash write and no FPGA SPI flash write.
Fresh USB status: FAT mounted, drives0–3 READY, commands/errors/dropped0,
CSR/request0000, last_error none. Both serial captures open, monitor PID27144,
logs build/serial-logs/20261028T212939Z. Installation evidence and receipt:
build/step35-download/install/installed.json. Initial cable access raced USB
re-enumeration; retry succeeded, followed by successful final load.

Physical step35 retry PENDING. Restart configured diagnostic P002000/S000000
and RUN. Keep FPGA powered: this is a volatile SRAM installation. Earlier
sections below preserve historical preparation and investigation status.


### Step35 download package READY — dongles disconnected, NOT programmed

User requested all FPGA/STM32 artifacts prepared for download, explicitly
noting disconnected dongles. Promoted READ-CLC fix to production RTL with
permanent regressions. Final READ CLC ends its data phase; a later STC before
completion sets Overrun and is not sent to STM32 as CSR6. Classification is
latched for the whole STC pulse. Both command flag AND flag buffer qualify
completion, including backend completion before HP ENF. Normal20us software
response window retained; CHECK/WRITE/INIT and final WRITE/INIT STC+CLC work.

All22 controller variants and board/LED tests PASS. New tests reject old RTL
and a deliberately unsafe combinational-only suppression control. Tests cover
normal/final READ, late STC, completion before ENF and during held STC, valid
held STC during completion, new command, CRS/POPIO/reset, CHECK, WRITE/INIT
last-word preservation, phase/pulse/backend variants. Production CPU/SV model
passes steps1–35 at200ns/8us polling; actual C++ sanitizer suite and ARM build
PASS. No diagnostic patch. ISE minimum period8.345ns, meets50MHz.

New FPGA controller.bit SHA256:
1c7f3790170f5b56724b706f539eac732951aac8b27703935d741f8b40f02b46.
Compatible STM32 ELF/BIN/HEX rebuilt; ELF is unchanged5c509335... (same CHECK-DMA
firmware already installed). Source/build receipts refreshed; no C++ code change
needed for the FPGA-owned termination fix. ARM48256 flash bytes/22716 RAM.

Download bundle: build/step35-download/hp13210-step35-ready.zip, unpacked under
build/step35-download/ready/. Includes controller.bit, STM32 ELF/BIN/HEX,
optional Xilinx cable firmware, build/validation receipts, timing report,
SHA256SUMS and download instructions. Prepared receipt:
build/step35-download/prepared.json. Previous artifacts saved under previous/.

NO hardware/programmer/serial accesses during preparation. Installed FPGA is
still1557ca2... and installed STM32 is5c509335...; physical step35 still fails
until the new FPGA is installed and tested. No SPI flash writes. When dongles
are connected, confirm HP halted, halt STM32 for SRAM load, run FSMC checks,
reload FPGA to clear test state, verify existing STM32 ELF (reflash with fresh
verified backup only if needed), reset/run and confirm FAT/all4 READY/idleCSR.
Normal configured diagnostic restart P002000/S000000. Physical acceptance of
the prepared update remains PENDING.

### Step35 investigation: final READ CLC lost; isolated candidate passes

No hardware/production firmware/RTL changes. Supported SIMH32 passes step35:
final READ DMA has IOI+CLC+EDT, then the diagnostic's OVJ issues OTA+STC data.
SIMH clears dpd_xfer on CLC and sets Overrun for later STC while busy. Our
FPGA ignores data-channel CLC. Current CPU/SV model reproduces physical E64:
extra request observed9.92us after staging word30, within20us response window,
so backend stages31 instead of setting Overrun. Actual C++ sanitizer probe
reproduces this:10us=>31staged/OV0,50us=>30staged/OV1. Physical gap NOT measured.

Original READ worker (800ns wait,3000ns delay,1200ns probe) passes isolated
step35 with current transport and original CPU speed. Literal original whole
CPU/controller/backend step35 replay still gets E14 thenE64 under Verilator5.052;
do not claim that whole original combination passed. Step35 memory snapshot
comes from unpatched diagnostic execution in SIMH before the test.

Isolated FPGA candidate latches READ CLC, sets Overrun on later STC before
command completion, suppresses the invalid CSR6 request. Current CPU/SV model
passes steps1–35 at200ns/8us polling, still with20us normal response window.
Candidate is ONLY under build/step35-investigation/clc-candidate/; production
core is unchanged, no bitstream synthesized/programmed. Needs permanent
directed RTL tests and pulse/completion-boundary handling before promotion.
Do not blindly shorten the timeout: hardware normal READmax17us was observed.

See diagnostics/hp13210/read-overrun.md and build/step35-investigation/result.json
for detailed evidence, timing, hashes and limitations. SIMH comparison script
now has explicit step35 coverage. HP remains at the physical step35 failure;
installed images are still1557ca2... FPGA and5c509335... STM32.

### Physical retry: step34 PASSED; new halt at step35 missing READ overrun

User restarted after the CHECK-DMA installation. Fresh H0 banner, then
H46 READ IN STEP35; E64 STATUS IS000000 SHOULD BE020001; H51 CYL0000
HEAD01 SECTOR07 WORD COUNT0030 UNIT00. No step34/E13: the CHECK correction
has physical evidence of passing step34. Full diagnostic still does NOT pass.

Fresh STM32 status41commands/2errors (expected earlier seek E03/E02), dropped0,
all4READY, lastcommand2000/RAR0027/CSR0040. READmax17us, WRITEmax3us.
Trace CHECK/EC/CM advances to READ/TO/CM with no final OV event. Earlier
step32 WRITE does report OV/ZF/CM. Step35 intentionally forces READ overrun;
the missing020001 is the next issue. This capture alone does not establish
why its late read request was not detected. No hardware/code changes made
during this check. Preserve HP halt for investigation; both captures active.
Evidence: build/check-step34/check-dma-update/retest/result.json and raw logs.

### CHECK optional DMA repair installed — ready for physical diagnostic retry

User confirmed HP halted and authorized installation after validation. STM32
now offers actual image words during CHECK when HP requests DMA; after DMA
stops, CHECK still completes its count/EOC operation without Overrun. Count0
remains a no-op; exact remaining sectors succeeds, exceeding them sets EOC.
The100us data-start guard and20us response wait apply to the optional stream.
Normal READ/WRITE/INIT and500us independent seek behavior are unchanged.

Installed/verified ELF5c5093355bca40b0ded0a86a209554dcbd855b70b7281bb93a7872f1fd1f3e81
(48256 flash bytes,22716 RAM). FPGA rebuilt and loaded into volatile SRAM:
1557ca2fafc7f8e5ad8c1d8c4640e8ac14b6a3da533b59a6fad5da4f96a9a6bd.
No functional RTL change was needed: existing CHECK count flag gating avoids
stale DMA, and backend DATA writes already request valid CHECK DMA. Added
permanent RTL coverage for this staged-data path. SPI flash was NOT written.

All22 FPGA variants, board/LED tests, native actual-C++ ASan/UBSan suite and
ARM build PASS. New CHECK tests fail against the old backend. Native tests
cover no-DMA CHECK, actual data,128-word DMA/50-sector CHECK, partial/count-end
transfers, EOC boundaries, media failure, pending SEEK and timer rollover.
Updated CPU/SV timing model passes through step34 with200ns and8us polling;
this is SV backend evidence, not execution of C++ inside the CPU model.
ISE minimum period7.543ns, meeting50MHz. Diagnostic was not patched.

STM32 halted throughout FPGA load/FSMC checks, then FPGA reloaded to clear
test attention. Scratch/attention hardware readbacks PASS. Initial SWD backup
failed before erase. Retry backed up/verified512KiB, but source guard stopped
programming after a README edit. Refreshed build, then normal backup/verify/
program/verify/reset succeeded. See build/stm32-disk/programmed.json for the
verified512KiB backup and flash receipt. Built/programmed ELF hashes match.

Fresh post-reset USB: FAT mounted, all4 READY, commands/errors/dropped0,
CSR0000, seek-completion-valid0, startup100us/response20us. Both serial captures
remain active. No HP inputs sent. Physical step34 acceptance is PENDING with
this firmware; earlier physical failure was the previous image. Restart the
already configured diagnostic normally at P002000/S000000, then RUN.
Installation evidence/receipt: build/check-step34/check-dma-update/.

### Independent SIMH comparison overturns diagnostic-bug conclusion

User challenged the claim that step34 is a diagnostic bookkeeping defect and
requested SIMH and original Verilog comparisons. The claim was wrong: both
GitHub SIMH HP2100 release29 and the HP maintainer's supported release32 pass
step34 with the same unmodified revision1805 diagnostic memory. Supported
release32 also completes section1, halting normally atHLT102011 with S1000.
CPU2116/32KW/EAU, 13210A SC22/23, disposable blank disks; startup P2000/S0
for the step34 trace. At entry to step35 P004031, DMA CW3=0, flag1, DMRF0.
At001542 SFC06 falls through to001543 (successful DMAT return), unlike our
current CPU/SV model's failure branch. No diagnostic patch is needed.

SIMH's CHECK worker shares its READ path and supplies data when the data
channel requests it, while sector checking continues after DMA stops. The
original hp2116_verilog/tb_hp2116.sv CHECK worker likewise stages words while
handshakes continue, then advances through remaining sectors without waiting
for more handshakes. Our current firmware/model completes after consuming only
the count, which explains the incomplete DMA. Do not interpret the manual's
normal no-data CHECK usage as requiring suppression of every optional DMA.

Evidence: build/check-step34/simh/release32-retest.log, release32-debug.log,
section1.log; source build/reference/hp2100-release32/SCP/HP2100/hp2100_dp.c.
The literal original Verilog CPU/controller/backend replay currently fails
earlier at step2/E21 under Verilator5.052; it is not a demonstrated full pass.
A controlled replay restoring ONLY the original CHECK worker in the current
production-RTL/timing harness PASSES through step34, entering35 at105.549ms.
Evidence: build/check-step34/reference-check-worker/run.log. Earlier seek and
transfer fixes remain in that controlled case. This isolates the CHECK backend
as the relevant difference; CPU instruction execution need not be changed.
scripts/hp13210_simh_compare.py repeats the independent supported-SIMH cases.
Hardware, production firmware/RTL and diagnostic memory remain unchanged;
physical acceptance still fails atstep34. The backend repair should preserve
count/EOC progression without DMA while supporting optional data handshakes,
as SIMH/reference do. Reverting only the FPGA flag gate yields one stale word
with the present backend, not a working implementation. See
diagnostics/hp13210/check-data.md.

### CHECK flag fix installed — hardware now matches zero-word CPU failure

User restarted atP2000/S0 after installation. NEW physical capture: H0 banner,
H22 CYCLIC CHECK IN STEP34; E13 0000 WORDS TRANSFERRED0128 EXPECTED;
H51 CYL0000 HEAD01 SECTOR21 WORD COUNT0128 UNIT00. This matches the CPU model.
Phantom one-word DMA is gone, but step34 is NOT fixed. Fresh STM3240commands,
2expected seek errors, READmax6us/WRITEmax3us, lastcmd6000/RAR0035/CSR0040.
Trace final CK/EC/CM, no E64 status mismatch. No hardware changes this check.
Evidence build/check-step34/install/retest/; aggregate hardware receipt updated.

Source follow-up: step34 arms READ DMA128 specifically to detect CHECK opcode
misdecode, outputs sector count50, issues CHECK6000, calls DMAT then STAT/WEND.
DMAT checks command flag then DMA flag; incomplete DMA flows FTCX -> MC -> count
read -> DMERQ/E13. Source revisions1432/1644/1805 all have this sequence, no
explicit DMRFC in step34. Manual3-28/29 says CHECK performs no sector data
transfer and signals command completion at EOC/count end. Remaining mismatch
between diagnostic DMA-completion handling and emulated CHECK is unresolved;
don't fabricate128 data transfers or patch diagnostic to force a pass. Need
trace this path in the now hardware-matching CPU model. Both captures active.

User explicitly requested installation. Production core now suppresses the
STM32 DATA-read contribution to HP data flag for CHECK only. Permanent test
fails on old RTL, passes across22 controller variants; READ/WRITE/INIT still
request DMA, CHECK CSR6 clears, command completion retained. Board/LED tests
and22 Python tests pass. ISE board build meets50MHz; min period7.543ns.

Loaded new FPGA into volatile SRAM via JTAG, ST-Link-halted STM32 throughout.
Bitstream SHA256afa0fd01df93adc300c882faa7c80f40d295ceb402de64f3847f0b42c6f9a80c;
core a117015b0ba9dcd366541fd4e0b9b59ae6db060f2d1afabb476e2fdae1021300.
SPI flash untouched. Previous f9d066... image/receipt saved in
build/check-step34/install/previous-fpga/. Physical scratch/attention readbacks
PASS, then reloaded same new bitstream to clear test attention. Existing STM32
49ae577... ELF verified48500bytes via SWD, reset/run after FPGA installation;
STM32 flash was NOT rewritten. Fresh USB FAT/all4READY, commands/errors0,
CSR0000, data-start100us/response20us. Both captures still PID8619, HP2400/7E2.

IMPORTANT limitation: full CPU run with new RTL does NOT pass step34. It now
prints E13 0000 WORDS TRANSFERRED0128 EXPECTED rather than one unwanted word.
The phantom transfer is removed, but remaining DMA/completion behavior needs
investigation. Do not claim full step34/diagnostic acceptance. User explicitly
told this before installation. Next physical run from P002000/S000000 will
determine actual result. No HP inputs or panel actions during installation.

Receipt build/check-step34/install/installed.json records sources/log hashes,
JTAG load, FSMC checks, STM verification, fresh status and CPU limitation.
Aggregate build/hardware-update-20261028.json updated; prior snapshot saved.
See diagnostics/hp13210/check-data.md. Hardware test pending.

### Current response/startup timing revision — installed and verified

User confirmed HP halted. Reloaded unchanged FPGA f9d066... into volatile SRAM
with STM32 halted, then backed up/verified512KiB old STM32 flash and programmed,
verified/reset new49ae577... ELF. Backup:
build/stm32-disk/backups/before-disk-backend-20261028T171843073236Z.bin.
Fresh USB status confirms100us data start/20us response wait, all4READY,
FAT mounted, commands/errors/dropped0, CSR0000, observed response maxima0.
Capture PID8619 still owns HP /dev/ttyUSB4 at2400/7E2 and STM32 /dev/ttyACM0;
USB reconnected automatically, no ACL repair needed. No HP input sent during
update. SPI flash untouched. Already configured: normal restart P002000/S0.
P100/S14 is the separate I/O configuration entry, not the normal restart.
Physical run now reaches step34; full diagnostic acceptance remains pending.

NEWEST result after proper P2000/S0 restart: fresh H0 banner and normal backend
activity. Passed earlier failing READ26 and intentional WRITE-overrun32, then
step33 EOC write. Halt reported A13/B4/code102001. Exact console H22 CYCLIC
CHECK IN STEP34; E13 0001 WORDS TRANSFERRED 0128 EXPECTED;
H51 CYL0000 HEAD01 SECTOR21 WORD COUNT0128 UNIT00. Fresh status40commands,
2errors (seek E03/E02), READmax6us/WRITEmax3us, lastcommand6000/RAR0035,
CSR0040. Trace step32 WR/TO/OV/ZF/CM, step33 WR/EC/CM, step34 CK/EC/CM.

Found/reproduced in isolated production-RTL simulation: any STM32 DATA read
reasserts HP data flag, including CHECK sector-count consumption. That creates
an unwanted DMA request in step34, which arms READ DMA to catch a misdecoded
CHECK opcode. Manual3-28 says CHECK performs no data transfers. Isolated
candidate gates stm32_read_7900_data_negedge with ~command_is_check_data ONLY
in set_data_channel_flag_buffer; count IRQ acknowledgement remains unchanged.
Candidate test confirms SRQ stays0, CSR6 clears, and command attention still
sets command flag. Production RTL NOT changed; bitstream/firmware NOT rebuilt
or reprogrammed during this check. Candidate needs permanent regression test,
full CPU step34 validation and normal RTL/build checks before hardware use.
Evidence/candidate under build/check-step34/, result.json includes source/log
hashes, HP console and fresh STM32 status. User told to keep HP halted.

Earlier reported A64/B4 after update: console at17:20:34Z says H46 READ
IN STEP26; E64 STATUS IS040001 SHOULD BE000000; same E47 word8 mismatch as
previous run.040000 is First Status, not Overrun020000. Crucially fresh STM32
? still commands0/errors0/seek-completion-valid0, response maxima0, CSR0040.
No new H0 banner, startup seeks, WR or RD events since firmware reset. Thus
no backend transfer with new timing has executed; likely resumed old failure
path, not established fresh diagnostic startup. No hardware resets/changes
made during this check. Initially asked user P100/S14 RUN then report haltcode/P
(expected102074/P012307); that request is superseded below. Evidence in
build/transfer-timing/retest-after-update/. Do not classify this as a new20us
transfer-timing failure merely from A64 or the repeated step26 label.

User objected to re-entering configuration; agrees execution switches should
be0, thought normal address100. Rechecked original Rev1805 source part01
header: CONFIGURATION ADDRESS100, STARTING ADDRESS2000. Part03 ORG2000 START
initializes globals and prints H0. Both configured.hex and section1.hex retain
100=124512,512=012231,2000=107700; INIT at12231 ends HLT74 then indirect JMP2000.
Clarify: S0 is right for execution, but direct normal restart is P002000/S0;
P100 is I/O reconfiguration, where S14 specifies disk data/command14/15. Don't
mistake leaving S14 set after configuration for normal execution: its bits2/3
request tables/custom program. No firmware/FPGA changes during clarification.

After the physical step26 regression, user requested simulator study and timing
adjustment before another attempt. Prepared backend adds100us initial data
delay after command/image read for READ/WRITE/INIT, separate100us first-WRITE
setup/CHECK count, and20us subsequent software response wait. SEEK500us unchanged.
CSR-pending data is accepted before checking deadline; only an empty expired
poll starts sector closing. This tolerates service stalls but cannot precisely
timestamp whether a pending word arrived late. Existing6.4us/word sector closing,
late discard, zero fill and CHECK behavior retained. USB reports READ/WRITE
observed response maxima (poll times, not edge timestamps).

CPU experiment exposed a second race: immediate two-word WRITE can finish
before diagnostic DMAT first samples the DMA count, entering a long fallback
wait and producing the old step32/E64 expected020001/actual000000. Initial data
delay prevents this in tested cases. It is a startup guard, not measured disk
rotation. scripts/hp2116_transfer_timing.py prepares/optionally runs an isolated
production-RTL+original-CPU/DSN151302 experiment; its backend is SV, NOT C++.
Final tests all PASS: CPU_SCALE15 with0.2us/8us poll delays through step32,
CPU_SCALE31 with8us poll delay through27; six-us control truncates step24.
Bounded scope, not full section1/RTE acceptance; exploratory slower-CPU runs
beyond32 stalled around REFINE/CHECK and remain unresolved.

Actual C++ full ASan/UBSan suite PASS, including default100us startup/rollover,
normal3/6/12/19us jitter over2..512words, delayed pending polls12/25us,
READ/WRITE50us late-word discard/zero fill, existing seek/CHECK/error regressions.
ARM build PASS48060flash bytes/22716RAM, validated ELF
49ae577c709e1a87104d021f4d7f624744ed1bae293f05ba98b73a6ba5ddabe8.
Previous built/installed6us artifacts preserved under
build/transfer-timing/installed-before/. Native/ARM logs and CPU acceptance
under build/transfer-timing/. See diagnostics/hp13210/transfer-timing.md.
Hardware now runs49ae577...; built/source/programmed hashes all match. Aggregate
build/hardware-update-20261028.json and build/transfer-timing/acceptance.json
updated with verified programming receipt, logs, backup and fresh status.
No FPGA RTL changes; bitstream f9d066... remains current. Physical test pending.

### Previous firmware: six-us sector-closing revision

NEW PHYSICAL RESULT after successful configurator reload: diagnostic starts,
but timing firmware REGRESSES to READ step26 (previous version reached32).
Captured H46 READ IN STEP26; E64 STATUS IS020001 SHOULD BE000000;
E47 DATA WORD0008 IS066550 SHOULD BE155320;
H51 CYL0000 HEAD00 SECTOR00 WORD COUNT0128 UNIT00.
Initial S14 was retained into table questions. Answered NO to cylinder and
pattern changes; user confirmed S=0 before second NO, so remaining setup
questions skipped and diagnostic ran. STM32 trace:14commands/2errors,
two WR/TO/CM then RD/TO/OV/CM. E03/E02 occurred in seek tests as expected.
This implicates overly tight6us response timeout/firmware timing, but actual
hardware interword latency has not been measured. No further firmware or
FPGA changes made. User told to leave HP halted; preserve current raw logs.
Physical overrun acceptance FAILED; fix normal-transfer regression before
claiming step32 timing correction works. Both serial captures remain active.

Latest user retry after installation: diagnostic did not start correctly.
NO new HP bytes captured; HP raw remains173bytes containing only the earlier
step32/E64 message. Monitor PID8619 still owns both ports; stty independently
confirms HP2400/7E2. Fresh STM32 ? report after the failed start: all4 READY,
commands0/errors0/CSR0000/request0000, so no new backend commands dispatched.
No reset or additional firmware change during this check. Requested current
HP P/A/B (octal), RUN/halt state and haltcode to locate where startup stopped.
Do not claim the overrun update has passed a physical diagnostic run.

Startup follow-up: user starts P=000100/S=000014, expects HLT102074,
but HP keeps running; manually halted at P=077373. Offline reference
configured.hex has 077372=102316 (SFS16), 077373=027372 (JMP077372),
077374=102516 (LIA16): configurator terminal-input wait, not inherently
corrupt memory. Reference terminal SC16 is simulation configuration only;
need actual HP words before identifying its patched select code. Diagnostic
source confirms S low6 bits at P100 are disk DATA select code, so S14 is
correct and must not be changed to simulator's initial configurator S16.
Original configurator and DSN151302 ABS records all pass checksums;
configurator loads000002..007677 before relocation, diagnostic000100..012402.
User panel readback: 000100=124512, 077372=102311, 077373=027372.
These match diagnostic JMP CNFIG,I and the relocated terminal-input loop
patched to SC11 (octal). They establish intact sampled words, not all RAM.
Source INIT (Rev1805 part08) only reads switches, patches channel/DMA words,
and HLT74; it has no terminal-input call. Reference CNFIG pointer at000512
is012231; INIT012231=015130 calls SWR001130 (switch reader, LIA1).
Thus unexplained diversion to terminal input persists; reloading DSN151302
is the next recovery step, keeping S14 for configuration. No HP input sent.
Host-escalated check confirms capture PID8619 still owns both serial ports.

User now explicitly authorizes HP console interaction with configurator:
line printer NONE, paper-tape input2748,12, then ready diagnostic tape and
enter 7900 DSN151302. This supersedes receive-only restriction for these
specific replies. Existing capture still reader, HP2400/7E2 confirmed.
Started build/serial-logs/configurator-replies.py (exec session32211), watching
NEW hp.raw output from byte173. It sent paced NONE then2748,12 after matching
prompts at16:47:45Z/16:47:46Z, recorded hp-transmissions.jsonl, and exited
successfully at DSN prompt. Captured2100,DMA,MPRT,32K MEMORY; both replies
echoed and accepted. HP now says READY DIAG. INPUT DEVICE and waits at
DSN(,SEQ.DIAG.EXECUT.). User has been asked to ready7900/7901 DSN151302 tape
on PTR, leave HP running and confirm; DO NOT send DSN before tape readiness
confirmation. Capture remains active; helper32211 finished. If user chooses
own terminal instead, release HP capture explicitly.

User confirmed tape ready; sent151302+CR paced at16:48:42Z and captured
its echo. No subsequent console text yet; load completion requires panel
halt confirmation (reference configurator completion HLT102077 atP077237).
Do not claim successful load based on echo. After successful configurator
load halt, diagnostic setup is P100/S14 then HLT102074; execution switches0.
User subsequently confirmed diagnostic loaded correctly and is starting it.
Reminded P100/S14 -> HLT102074 -> S0/RUN; fresh physical diagnostic result
pending. Both raw captures continue; no firmware/FPGA changes during reload.

User explicitly requested fixing timing after step32. STM32 firmware now has
separate100us first-write-word/CHECK-count setup and6us interword response
deadlines (manual5.9us rounded to microsecond clock). Main FsmcBus samples
micros() after bus accesses to avoid subtracting their time from next response.
Manual table1-1 gives156250words/s ->6.4us/word. After a word timeout, separate
READ/WRITE drain states keep Busy/command incomplete through remaining sector
words at that rate. Late strobes are acknowledged/discarded and set Overrun;
WRITE preserves valid prefix and zero-fills sector tail. Late READ does not
stage another word. INIT retains zero-attention completion. Full-cylinder EOC
retains previous behavior. No FPGA RTL changes.

Final post-SD-write CSR poll catches late words arriving during blocking I/O
and retains command/RAR packets instead of losing destructive CSR reads.
New OV trace code identifies late-word status (not an E-code/fault counter).
USB status prints6us response/6.4us word timing. This remains firmware polling
with microsecond quantization/interrupt latency, not hardware edge timestamps.

Old firmware fails new late-third-word regression. Complete native ASan/UBSan
suite PASS, including WRITE/READ lateness, discard/zero-fill, timer rollover,
late SD-write strobe plus pending SEEK, normal5us gaps/6us boundary, first-word
setup, INIT completion, sector lengths1/2/30/127/128/129, and existing106 CHECK
cases. Native50us late-word repro: Overrun1, persisted third word0000, notBEEF.
ARM build PASS:47844flash bytes,22704RAM. New ELF
SHA25651334371b8277d2969a159c77ce559b70fa2af9125a0cd0f1f022b06ed68fef9.

Installed/verified/reset. First ST-Link reset/probe failed before backup or
erase; full backup/verify/program retry succeeded. Verified512KiB backup:
build/stm32-disk/backups/before-disk-backend-20261028T162911377457Z.bin.
Programming receipt build/stm32-disk/programmed.json matches current build.
While STM32 halted, reloaded unchanged validated FPGA f9d066... SRAM image
to clear old transfer state before starting new firmware. SPI flash untouched.

New post-reset USB reports confirm FAT/all4 READY, commands/errors0, CSR0000,
response6us/word6.4us/seek500us. Both monitors remain ACTIVE under
build/serial-logs/20261028T160755Z/. HP remains halted; restart diagnostic from
normal beginning. Physical overrun acceptance is PENDING; do not claim step32
passes until a new run. Evidence/source/log hashes under
build/write-overrun-investigation/acceptance.json. Aggregate current receipt
build/hardware-update-20261028.json updated, previous receipt preserved.

### Latest diagnostic: step32 WRITE missing overrun (CHECK fix passes)

User reported A64/B4/HLT102001. Exact captured console:
H45 WRITE IN STEP32; E64 STATUS IS000000 SHOULD BE020001;
H51 CYL0000 HEAD01 SECTOR07 WORD COUNT0002 UNIT00.
This is NEW: step30 cyclic check and step31 read/data verification advanced
without a reported error. Trace has eight CK completions, no CHECK timeouts,
and EC on the final49-sector case. CHECK correction now has physical evidence.

Step32 intentionally writes two words, then issues a late third word (source
comment ~50us later) to expect Overrun+any-error020001. Manual3-61 specifies
5.9us maximum DMA response and overrun for a late transfer before command
completion. C++ write path currently has a100us word gap and NO write-overrun
detection/late-word discard during sector padding/completion. Reference SV
worker does include a post-timeout overrun check. Do not just lower the gap
or set a flag without preserving zero-fill/discard behavior (later step35
checks the overrun word was not written).

Native reproduction on current backend: two words, third wordBEEF at+50us,
then timeout -> consumes3 words, persistsBEEF, Overrun0. This demonstrates
the software gap; physical word timing is NOT measured by USB trace drain
timestamps. Actual final trace WR/TO/ZF/CM has no Overrun indication.
Fresh USB status:36commands,2errors,trace_dropped0,last_errorE02 (the earlier
deliberate busy-seek test; E03 also expected earlier), last command1000,
RAR0027 (head1/sector7), CSR0040. All drives still READY.

Evidence/snapshots/repro: build/write-overrun-investigation/halt-20261028.json
and repro-before.cpp/log. This was the failure BEFORE installing the current
overrun correction above. Full diagnostic acceptance remains pending.

### Connections and reload before that run

User confirmed HP halted and requested latest images and all USB/serial checks.
Xilinx cable initialized with known xusb_emb.hex (03fd:000d ->0008); JTAG
identifies XC6SLX9 0x24001093. ST-Link identifies STM32F407, target3.269V.
Both validated local images STILL match current source fingerprints; no code
change or rebuild required. STM32 flash independently verified47868 bytes
against CHECK-fixed ELF3f9c7321d0070602162dd5b531d52ce05062e63b9a72e667e17ea1946dd7d9df.
It already contained the latest firmware, so flash was not rewritten.

STM32 halted while FPGA SRAM reloaded with validated controller.bit,
SHA256f9d066de0874ff1842ba0dfd1eca3f617e6afea89eca957511456a794edf4448.
Physical FSMC scratch A55A/5AA5 and attention0/1/latch-preservation checks pass.
FPGA reloaded once afterward to clear test state; then STM32 reset to run.
SPI boot flash is still unchanged/old: FPGA load remains VOLATILE and must
be repeated after a power cycle. No physical diagnostic acceptance yet.

New capture ACTIVE: build/serial-logs/20261028T160755Z/ (monitor-reconnect.py).
HP FTDI AH01E1EM /dev/ttyUSB4 open at2400 7E2; no HP bytes received while
halted. STM32 USB378035813433 /dev/ttyACM0 open; user now belongs to dialout,
so no per-reset ACL repair needed. Other ttyUSB0-3 belong to laptop modem.
Repeated fresh USB reports: FAT mounted, drives0-3 READY, zero commands/errors,
CSR0000/request0000, fixed seek500us. The old CSR0040 pending strobe is gone.
HP input was not sent and HP remains halted. Ready for normal diagnostic
startup; investigate startup/entry if it still fails to begin, rather than
assuming the previous CHECK correction has passed on the physical machine.

Receipts: build/hardware-update-20261028.json,
build/controller-board/sram-downloaded.json,
build/stm32-disk/flash-verified-20261028.json. Previous programming receipt
still correctly records actual STM32 flash write on2026-10-26.
Older stopped-monitor and firmware-state paragraphs below are historical.

## Laptop update — 2026-10-26

## Overnight stop: diagnostic no longer starts after CHECK firmware update

User stopped for the night and reports: "The diag is not starting at all now."
Do NOT treat CHECK fix as accepted on hardware. Native tests and flash verify
passed, but the next physical diagnostic attempt did not start. Cause unknown;
investigate startup/reset state before another firmware change.

Latest USB status after CHECK update showed all4 READY, commands0/errors0,
CSR0040 (pending old data strobe). No new HP text was captured after the
earlier step30 E64 message; no new disk commands were captured after flashing.
Both serial devices disconnected around22:14 Stockholm time; hardware power
state was not independently checked. Serial capture is now STOPPED for the
overnight pause. Logs preserved in build/serial-logs/20261026T205931Z/ and
summary build/check-data-investigation/overnight-state.json.

Next session: check USB/dongles and HP halt/panel state, reload the FPGA
SRAM image if power was cycled (SPI boot flash is still old), then restart
logging and inspect startup/POPIO, pending data request and diagnostic entry.
STM32 flash retains CHECK-fixed ELF3f9c7321d0070602162dd5b531d52ce05062e63b9a72e667e17ea1946dd7d9df.
FPGA SRAM image to reload is build/controller-board/controller.bit,
SHA256f9d066de0874ff1842ba0dfd1eca3f617e6afea89eca957511456a794edf4448.
Older "monitors active" paragraphs below describe earlier points this evening.

## Current firmware: autonomous CHECK fix installed and verified

User requested the CHECK correction after step30 E64. CHECK now accepts its
single six-bit sector-count word and completes without dummy HP words or
per-word STCs. A request exactly covering the remaining two-head cylinder
succeeds; exceeding it sets EndCylinder before the zero-attention command
completion write. Zero remains a no-op and missing count still times out E10.
READ/WRITE retain their existing word handshakes. No CRC/media-fault model
was added. FPGA source/image and 500 us seek delay are unchanged.

New regression fails on the old backend at the 49-sector EOC assertion and
passes after the change. Full native ASan/UBSan tests PASS. Added106 CHECK
cases cover actual step30 counts, every drive/head at sectors0/7/23 on both
sides of EOC, zero and masked count bits, without artificial HP data strobes.
ARM build PASS: flash47428 bytes, RAM22700 bytes. Programmed/verified/reset
new ELF SHA2563f9c7321d0070602162dd5b531d52ce05062e63b9a72e667e17ea1946dd7d9df.
Verified512KiB backup build/stm32-disk/backups/before-disk-backend-20261026T211030207970Z.bin.
The first backup attempt failed after12KiB before programming; that partial
file is not a valid backup. A fresh full backup/verify and programming retry
succeeded. Receipt build/stm32-disk/programmed.json matches new build sources.

User restored the STM32 serial ACL after reset. Both monitors active in
build/serial-logs/20261026T205931Z/. Two NEW USB reports after programming:
FAT mounted, drives0-3 READY, zero commands/errors/trace_dropped, seek500us.
CSR0040 retains an old HP data strobe; HP remains halted. User was asked to
restart the diagnostic from its normal beginning after the firmware reset.
Physical step30 acceptance is pending; do not claim it passes on HP yet.
Evidence/source/test/log hashes: build/check-data-investigation/acceptance.json.
Aggregate current-image receipt build/hardware-update-20261026.json updated;
previous receipt preserved as hardware-update-before-check-fix-20261026.json.

## Latest physical diagnostic: reaches step 30, CHECK DATA missing EOC

After both downloads below, user ran DSN151302 and corrected reported A to
64 (B=4, same error halt code). Captured HP console gives exact failure:
H22 CYCLIC CHECK IN STEP 30; E64 STATUS IS 000000 SHOULD BE 000041;
H51 CYL 0000 HEAD 00 SECTOR 00 WORD COUNT 0049 UNIT 00.
This is later than the former SEEK failure. Trace includes successful seeks,
write/read/refine commands, and eight CK / TO / CM sequences. E03/E02 occur
during the diagnostic's deliberate invalid/busy seek checks; no E04 observed.

Root cause reproduced against the actual C++ backend with NO hardware changes:
CHECK consumes sector count, then enters the READ-style dummy-word/STC loop.
HP supplies no per-word strobes for cyclic check, so it times out after one
dummy word and completes without advancing to end-of-cylinder. Native repro
for counts 1,2,4,8,16,32,48,49 shows timeout=1, dummy_words=1, EOC=0 for ALL.
Diagnostic source 12960-18004 Rev1805 step30 explicitly expects 48 sectors to
succeed and 49 to set EOC+any-error (octal 000041). Manual paragraphs3-28/29:
CHECK performs internal sector checks without HP data transfers until count
exhausted or EOC/error. Thus missing 000041 is explained by CHECK incorrectly
depending on HP data strobes, not another seek-completion race.

Evidence/snapshot and native repro under build/check-data-investigation/;
original live serial logs remain build/serial-logs/20261026T205931Z/.
This failure was recorded BEFORE the autonomous CHECK fix installed above.
The former backend emitted a dummy word and timed out; the corrected native
repro emits no dummy word, no timeout, and sets EOC only for49 in this series.
HP remains halted; both serial captures active; physical retry is pending.

## Current hardware: both updated after power-up (2026-10-26)

User confirmed HP halted and explicitly requested both downloads. Xilinx cable
initialized from 03fd:000d to 03fd:0008 using xusb_emb.hex; JTAG identifies
XC6SLX9 0x24001093. ST-Link identifies STM32F407, 512 KiB flash.
Latest production controller built for the actual carrier, board/LED sims pass,
ISE timing passes 50 MHz (minimum period 7.077 ns). Loaded over JTAG into SRAM:
bitstream SHA256 f9d066de0874ff1842ba0dfd1eca3f617e6afea89eca957511456a794edf4448.
Core SHA256 remains 66c81e689de6d18ac1a102e245b24ad3d5f071349fc269cf02ab2616ddb16bb7.
STM32 was halted during FPGA replacement. Hardware scratch A55A/5AA5 and
attention 0->0, 1->1, 0->1 readbacks pass (attention is an OR latch).
FPGA reloaded once afterward to clear temporary test state.
SPI FLASH NOT WRITTEN: FPGA image is volatile and must be reloaded after
power cycling; old boot flash remains. Receipt build/controller-board/sram-downloaded.json.

New STM32 backend programmed, verified and reset. ELF SHA256
18fa6512894eeace422c3c4ee81f37e82290298e1da64c873869f725a6fd0e54.
Fresh verified 512 KiB backup:
build/stm32-disk/backups/before-disk-backend-20261026T205801897854Z.bin.
Programming receipt build/stm32-disk/programmed.json. Two USB status reports
confirm FAT mounted, drives 0-3 READY, commands/errors/trace_dropped all zero,
fixed seek delay 500 us. This is the firmware with busy-seek recovery fix.
No physical disk diagnostic or sector-transfer acceptance yet after these updates.

Serial monitors ACTIVE under build/serial-logs/20261026T205931Z/:
HP console FTDI AH01E1EM /dev/ttyUSB4 at 2400 7E2, STM32 /dev/ttyACM0.
The other ttyUSB0-3 devices belong to the laptop modem. USB reset removed the
STM32 serial ACL; user restored it with sudo setfacl -m u:mattis:rw /dev/ttyACM0.
Monitor build/serial-logs/monitor-reconnect.py keeps HP open and retries STM32
after disconnect/permission changes; sends ? only to STM32, never HP input.
Aggregate verification build/hardware-update-20261026.json. User can retry
the diagnostic now. Older 'not downloaded' and SRAM hash paragraphs below
describe superseded states, not the current running images.

## RTE-II boot regression with production RTL

User requested RTE-II as a broader regression after the SEEK correction.
Both 500 us and 4000 us seek cases PASS: disk bootstrap, SET TIME, ON,FMGR,
DL with SYS/AUX labels and directory headers, then return to FMGR prompt.
The actual CPU/DMA loads RTE from the original image; no memory checkpoint.
Each run captures 17 SEEK and 30 READ requests, including 13 seeks whose
completion attention was suppressed by CLC. This exercises READ submitted
before positioning completes, with the worker finishing movement while
suppressing the seek's attention. CLC does not cancel drive positioning;
the internal seek_aborted latch refers only to completion attention.
No WRITE requests occur. No additional controller or firmware changes needed
for this boot test; no hardware programmed.

Run `python3 scripts/hp2116_rte_boot.py --run --out build/hp2116-rte-boot/final`.
The script prepares isolated sources, builds with pinned Verilator Docker,
and checks console output, unexpected halt and timeout. Final receipts/logs
under that directory match source/generated/log hashes. Final simulated
completion times 336.016 ms / 374.394 ms. Forced MAX_MS=1 fails explicitly.
Original disk/loader files unchanged; simulated writes are not persisted.

Limits: this uses the SystemVerilog backend model, not the C++ ARM image or
physical HP. Numeric fields in DL are garbled (e.g. CR=;;;;:), also visible
in the reference boot screenshot; their cause/correctness is not established.
Only labels/headers and return to prompt are checked. A 1 ms console-reply
experiment failed to reach FMGR at both seek delays; final tests retain
the original 20/100 ms reply delays. Exploratory logs are separate from final
acceptance. See diagnostics/hp13210/rte-boot.md for details.

## SEEK correction in production RTL (not downloaded)

User authorized changing Verilog and validating seek behavior. The current
source differs from the SRAM image still running on the board. SEEK now
requests backend service at RAR acceptance but only raises HP flag on backend
attention. ADDRESS RECORD remains immediate. Extended tests exposed and fixed
STATUS suppressing SEEK attention (step21 E10), wrong-drive abort selection, Busy appearing
too late, and acknowledgements lost under overlapping/wide STC,C strobes.
An eight-packet command/RAR FIFO now prevents a later STATUS or closely spaced
SEEK from replacing a pending backend request. CSR consumes one packet;
COMMAND/RAR expose its snapshot until RAR is read; abort bits remain live.
The existing STM32 backend already uses this read order. Extended native tests
also exposed a busy-seek recovery issue: backend.cpp now retains Busy and defers
attention until the original positioning worker finishes, instead of signalling
an early busy-error completion. Invalid addresses also clear internal Seeking.
This firmware correction is built/tested but NOT programmed; the running image
is unchanged. New ARM ELF SHA25618fa6512894eeace422c3c4ee81f37e82290298e1da64c873869f725a6fd0e54.

All22 updated 50MHz controller variants, board/LED sims,22 Python tests and
native ASan/UBSan backend tests pass. Native seek geometry coverage adds64
valid/all-head/all-drive boundary cases and16 invalid cylinder/sector cases.
ISE smoke receipt matches current RTL, minimumperiod5.751ns; no bitstream
downloaded. Final six seek/recovery cases ALL PASS under
build/hp2116-seek-validation/recovery/; acceptance.json records source hashes,
checkpoint/log hashes, timing settings, and receipts. Cases:500us/4000us seek,
20us/2ms backend capture latency, combined4ms seek+2ms capture, and8x wider CPU
strobes. Each runs actual S1 steps1,2,21,22,23 plus successful recovery SEEK in
step24 and stops BEFORE first WRITE executes. Native tests confirm busy-seek
error waits for original completion and a subsequent valid seek succeeds.
Earlier acceptance/ runs passed through entry to step24 before the final backend
recovery correction; release/validated contain exploratory failures.
See diagnostics/hp13210/seek-validation.md for protocol and testing details.

Full CPU simulator now saves configured.hex at initial HLT74 and section1.hex
at original S1 entry003137, after startup initializes globals (NFFB etc).
FAST_MEM replays memory with reset peripherals; SECTION1_ONLY must use
section1.hex, not configured.hex. STOP_AFTER_SEEK_STEPS requires reaching
step24 after steps1,2,21,22,23; final STOP_BEFORE_FIRST_WRITE also verifies the
recovery SEEK in step24. Capture latency is injected per new IRQ burst;
backlogs are drained. Simulated Busy publication is synchronous before fork,
matching actual Backend::dispatch and avoiding a reference-worker ordering race.
Reference submodule untouched. The corrected hardware image from earlier is
still SRAM-only and the running STM32 seek delay is still500us.

Full HP2116 CPU simulation now reproduces the hardware E21 using the actual
DSN151302 binary plus the corrected board controller core. See
diagnostics/hp13210/seek-timing.md and scripts/hp2116_seek_timing.py.
The script copies sources into ignored build/hp2116-seek-timing/ and never
edits the reference submodule. Verilator image 5.052 is available locally.
core-500us.log: step2 RAR done at467560695ns; HP flag at+0.130us with
attention0; backend captures3038 at+0.760us; HP reads attention0 at+103.360us;
STATUS OTA at+106.860us; completion at+501.870us sees003C/abort1. E21 final
P012136 A000021 B000004. core-late-capture.log adds2ms backend capture delay:
startup and step2 requests collapse into one pending bit; first capture003C;
same E21. core-4ms.log instead fails E64 in step1 (busy status000005).
These reproduce both observed SK/SA and unsupported-request failure modes.
Completed comparisons: core-50us.log reaches cylinder1 in step21 with existing
flag behavior (short delay hides race). core-completion-only-late.log (500us
seek,2ms capture) and core-completion-only-4ms.log (4ms seek,no capture delay)
also reach cylinder1/step21 using a SIMULATION-ONLY change that suppresses
the early HP flag for SEEK while preserving backend IRQ and ADDRESS RECORD.
HP flag then rises on worker attention write; delayed capture still reads3000,
completion abort0,attention1. These runs intentionally stop at cylinder1;
they establish step2 progress, NOT full diagnostic acceptance. core-slow-after-
config.log changes CPU divider1->15 at initialHLT74, after UART configuration;
it reports E63 NO DATA FLAG during startup step00, exposing a separate strobe/
handshake dependency. Do not count slowCPU as successful E21 timing control.
Experimental generated sources/runtime settings are hashed in
build/hp2116-seek-timing/sources.json. Verilator builds and diff checks pass;
reference submodule unchanged. Board RTL/firmware untouched by these simulation
experiments; corrected FPGA is still SRAM-only. Before applying any new board
change, extend simulation beyond step21 and check command/abort semantics.

500µs experiment result: HP again H44 step02/E21. New capture contains
D0 SK / D0 SC, then D0 ?? / D0 E04. Counters2commands/1error, latest
Command0x003C/RAR0/request0x00C0; completion snapshot valid1/raw0x3000.
Unlike prior4ms repeat, no SA in this capture; however source startup HLP2
also issues SEEK for ready drives, so captured SC cannot yet be assigned to
section1 step02. Do not claim shortening fixes the failing diagnostic seek.
Remaining issue is command/flag sequencing; avoid further blind delay tuning.
Need phase-correlated capture or standalone diagnostic-like status/seek path.
FPGA fix SRAM-only;500µs STM32 remains installed; both captures active.


**CURRENT STM32 SEEK DELAY IS500µs, replacing4000µs for a controlled test.**
User authorized experimenting with shorter timing. All seeks currently use
this fixed500µs delay; it is NOT yet cylinder-distance-dependent or a physical
drive timing model. USB status explicitly reports the configured delay.
Seek deadline/rollover/overlap tests now use the configured constant;
native sanitizer regression and ARM build pass. Previous STM32 flash was
backed up and verified; new image programmed/verified/reset successfully.
Current ELF SHA256: `d135a449820c33b860b9ca18759a493f9ccb60cf0d06e0c35fdb908636650af3`.
All four drives READY, zero counters/errors on startup. Both serial captures
running in build/serial-logs/20261026T190534Z/. Diagnostic retry is pending.
FPGA correction is still the previously verified SRAM image; no FPGA reset,
reprogramming, or flash write during this STM32 timing experiment.


User timing clarification: the reference's4ms seek delay was chosen only to
make DSN pass in simulation; it is NOT a measured real-drive requirement.
Treat firmware SeekTimeUs=4000 as tunable, not an authoritative hardware
constraint. Shorter completion is a valid controlled experiment. Existing
WAITS source calls a1ms delay before polling flag and permits105ms total;
this is not proof that completion must take4ms. Retain the distinction:
shortening delay may avoid the observed early flag/status/abort race, but
passing at one delay alone does not validate command IRQ/capture semantics.
No timing parameter or firmware changed in response to this clarification.


Latest repeated DSN run: same H44/E21 HP halt, but new STM32 trace D0 SK,
D0 SA (seek dispatched then attention suppressed), not new unsupported
commands. Counters5commands/3errors: error count unchanged from prior run;
last_errorE04 is historical. Dispatch Command0x3038/RAR0, completion
Command0x003C for drive0. Live OpenOCD read confirms Command0x003C and
Attention0x0000. Thus drive0 abort was clear at dispatch and set by completion,
with live opcode replaced from3 to0. Supports early completion/status race;
exact diagnostic bus timing still to reproduce before altering seek/flag RTL.
HP halted; no new resets or programming; current corrected SRAM image remains.


After successful standalone SEEK on corrected FPGA SRAM, DSN151302 retry
still failed H44/E21 at common halt P012136/M012135, user A21/B4. New trace
since standalone: D3 ?? E04, D0 ?? E04, D0 ?? E04. Counters now4commands/
3errors, last dispatch Command0x003C/RAR0/request0x00C0. No new SK or SC.
The valid completion snapshot0x3000 is retained from the earlier standalone,
not proof of a diagnostic seek. Current remaining issue is command capture/
handshake timing; attention zero-write corruption is independently repaired.
Candidate: FPGA set_irq_ff sets command flag at RAR completion, whereas seek
worker takes4ms. DSN WAITS polls after1ms and then issues STAT, which replaces
live Command with0 and can abort seek attention. Standalone intentionally
waited65536 increments and issued no STAT. Reference HDL also has early flag
behavior, so do not modify on speculation; reproduce realistic DSN path first.
Next useful test: diagnostic-like one-shot without the long settling delay,
preserving exact attention read and following status sequence, with retained
IRQ-time command evidence or simulated timelines to locate the race.
HP halted. Corrected FPGA remains SRAM-only; no power cycle.


Latest hardware acceptance: user reran unchanged seek-once at076000 on the
corrected FPGA SRAM image and reported A000001 at its halt. Captured STM32
trace D0 SK D0 SC; commands1/errors0/trace_dropped0, Command0x3000/RAR0,
completion valid0x1/drive0 raw0x3000. Standalone drive0/cylinder0 seek and
attention readback now work. Full DSN151302 remains untested after the FPGA
fix; disk-sector transfer/boot acceptance remains pending. Both logs active.


**CURRENT FPGA IS A CORRECTED VOLATILE SRAM IMAGE. Do not power-cycle yet.**
Write-contamination correction built, loaded over JTAG with STM32 halted,
and tested on hardware. SPI flash was NOT written; power cycling restores
the old defective write capture. Current bitstream SHA-256: `2228041eb63415d1898589663273358e9003d8016ac62290d14887056a762adc`.
Receipt: build/controller-board/sram-downloaded.json. ISE passes50MHz timing
(minimum period6.325ns). All22 controller variants, board/LED simulations,
and22 Python tests passed. Expanded tests assert NWE during address phase,
including NE permanently active, and test zero/one-hot attention plus zero
SET/CLEAR status masks. Pre-fix RTL fails the zero attention test; fixed passes.

Core now retains last qualified write data/address and commits once at
synchronized NWE rising edge. All FSMC write targets (CSR/data/attention/
status/scratch) use retained data. Existing read acknowledgement path unchanged.
After new FPGA SRAM load, direct hardware attention readbacks were:
initial0000; write0000 ->0000; write0001 ->0001 (twice).
Evidence: build/controller-board/attention-write-hardware.log.
STM32 was then reset to run; FAT mounts, drives0–3 READY, counters/errors0.
Both serial captures are active in build/serial-logs/20261026T185220Z/.
HP remains halted. Next user action: set P076000 and run the existing
seek-once program again, expecting P076031/A000001. Full diagnostic still
pending; do not claim it passes. Existing seek test binary remains valid.

Linux local Icarus10.3 launchers are in build/tools/bin; use on PATH with
Python3.12 for make test/controller-build. Compatibility edits remove
localparam reg syntax and a testbench sformatf; simulation runner explicitly
rejects FATAL output because this old vvp can return exit0 after fatal.
Ignored config/toolchain.local.json selects full ISE image/license MAC from
original handover; config/board.local.json matches example carrier pins.
No permanent FPGA flash update has been performed for this correction.


**Isolated hardware reproducer confirmed:** user set A030000/P076005 and
single-stepped OTA15 once, then left HP halted. Direct FPGA reads confirmed
Attention0x0000 and Command0x3000. A single OpenOCD halfword write of **zero**
to Attention CPU address0x6000000C then produced **0x0006**, repeated on
readback. No HP seek sequence or new firmware was involved. Evidence:
`build/stm32-disk/attention-zero-write.log`. This proves the attention write
path incorrectly adds bits1/2 on a zero-data transaction; the value equals
AD register address0x6. Strong evidence for multiplexed address/data capture,
though the precise sampling edge still requires waveform/simulation analysis.
Current attention is0x0006; do not interpret it as real drive attention.
HP remains halted after OTA15; no STC, reset, or programming performed.
Next: reproduce real FSMC address/write overlap offline, fix write-data
qualification/latching, regress all affected register writes, then build and
review before installing FPGA image. A local Icarus package is extracted in
build/tools/iverilog/root; invoke iverilog with -B pointing at its extracted
usr/lib/x86_64-linux-gnu/ivl directory (not installed system-wide).


Latest hardware result: standalone seek-once loaded from PAPERTAPE completed
at P076031 with A000007 (expected000001). STM32 trace D0 SK D0 SC;
commands=1/errors=0, request0x00C0, dispatch Command0x3000, RAR0;
completion valid0x1/drive0 raw0x3000 (not aborted). Direct running-target
OpenOCD halfword reads repeatedly confirm FPGA Attention at0x6000000C
is0x0007; Command at0x60000004 is0x3000. Therefore extra attention bits
are present on the FPGA/FSMC side, not merely HP readback corruption.
Strong but unproven candidate: Attention AD address0x6 being OR-latched
as write data during multiplexed address/data transition; address0x6 OR
intended drive0 bit0x1 equals observed0x7. Core attention writes are
level-sensitive while NWE active. Need waveform/simulation or directed
transport evidence before modifying RTL. Other possible stale/spurious
writes not yet ruled out. HP remains at standalone halt; preserve state.
Current serial capture: build/serial-logs/20261026T183953Z/ (active).
SD mount initially failed after reconnect; user confirmed card inserted,
explicit reset recovered FAT and drives0–3 READY. Xilinx RAM firmware was
reloaded; JTAG and ST-Link contact verified. PAPERTAPE/tapes/seek-once.abin
is the verified224-byte absolute image, copied without changing ptape.cfg.


Latest preparation after user returned: a 29-word one-shot SEEK test is ready
at076000–076034, generated by scripts/hp13210_seek_diagnostic.py; listing
in diagnostics/hp13210/programs/seek-once.lst. It matches diagnostic I/O
ordering, adds a65536-ISZ settling delay, captures attention in A, and halts
at076030 (P076031). No following status command. Expected A000001. Six
related offline tests pass. Not loaded/run on HP yet; no firmware change.
Attempt to restart serial capture failed: neither FTDI nor STM32 USB is
currently enumerated (only laptop modem serial devices). Capture is OFF.
Reconnect hardware and rediscover ports before running the test.


### End-of-day state — resume here tomorrow

User stopped work on 2026-10-26. HP is halted; the six-word standalone
command-latch loop at **076000–076005 octal** was examined and is unchanged.
The user reported the FPGA LED continuously lit even with HP halted; cause
not established. Do not dismiss that observation as rapid loop activity.
Earlier unexpected halt during full-speed execution was not reproduced;
there is no evidence that the program modified memory.

The last DSN151302 retry still failed H44/E21 (same error halt/registers).
This time STM32 captured `D0 ?? E04`, commands=1/errors=1,
request=0x00C0, dispatch Command=0x003C, RAR=0; no seek completion snapshot
was valid. Thus no seek was dispatched on that run, unlike the preceding
`D0 SK D0 SA` run. Reordering completion reads has not resolved the issue.

Standalone test generated by `scripts/hp13210_command_diagnostics.py`:

```text
076000 103100  CLF 0
076001 106715  CLC 15
076002 062005  LDA 076005
076003 102615  OTA 15
076004 026002  JMP 076002
076005 030000  command literal
```

User confirms 32K words; top-64-word loader at 077700–077777. Test moved
from 002000 to 076000 before being entered. DSN tape loads through 012402;
source documents lower normal buffers/custom workspace. Do not overwrite
DSN again or assume the custom-test builder will preserve high-memory code.
The loop issues no STC and starts no disk transfer. Direct ST-Link FSMC
halfword reads at **0x60000004** repeatedly returned **0x303C**: command
nibble3/drive0 correct; low0x3C is all four retained abort bits. This verifies
held command readback but not interrupt-time capture. The first inspection
briefly halted/resumed STM32; the latest reads worked while it ran:

```sh
build/stm32-tools/openocd/xpack-openocd-0.12.0-4/bin/openocd \
  -f interface/stlink.cfg -f target/stm32f4x.cfg \
  -c init -c 'mdh 0x60000004 1' -c 'mdh 0x60000004 1' -c shutdown
```

Next: confirm current hardware state, investigate persistent activity LED
with HP halted, then vary the held command/drive pattern at076005 and compare
actual Command readback (mask0xF303) before exercising STC/seek handshakes.
Do not infer command corruption solely from the missing attention; distinguish
live-register replacement, FSMC transport, and HP bus decode/timing.
Both capture files are under `build/serial-logs/20261026T170849Z/`;
serial capture is being stopped for the overnight pause. Restart explicitly.
HP port remains FTDI AH01E1EM /dev/ttyUSB4 at2400 7E2; STM32 CDC /dev/ttyACM0.
No further firmware changes/programming after the seek-snapshot build.
The reference submodule is now initialized at the pinned commit. Diagnostic
source archive and extracted revisions are in ignored build/reference/hp-diagnostics/.
There are uncommitted source/test/documentation changes; preserve them.


Latest retry preparation: first corrected-firmware run failed H44/E21 with
STM32 `D0 SK D0 SA`; dispatch command=0x3038, RAR=0, commands=1, errors=0.
HP is halted. Seek completion was changed to sample Command before clearing
seek status, matching the reference. Per-drive completion Command snapshots
and a validity mask are now reported by USB `?` without extra FSMC reads.
Native sanitizer tests (including ordering and retained abort/completion values)
and ARM build passed. This newer firmware was backed up, programmed, verified,
and reset; ELF SHA-256: `cf5a99b08b528ae37ba79f07a618e1d430afda1fc2ce5ea2660f58bf73b257ea`.
Both serial monitors restarted in `build/serial-logs/20261026T170849Z/`.
Startup confirms all four drives READY, zero commands/errors. Retry pending;
the ordering change is not yet proven to resolve E21. Earlier receipt/hash
below refer to the preceding firmware build.

The corrected STM32 disk backend has now been built, programmed, verified,
and reset to run on the Linux laptop. Native sanitizer regression tests passed.
A full 512 KiB flash backup was saved and verified before programming.
Receipt: `build/stm32-disk/programmed.json`; ELF SHA-256: `d0673b65da12f74cf1a721983d4daf0f455f29d7607c71e5ccc606d0d218ad6a`.
USB status after programming: FAT mounted, drives 0–3 READY, commands=0,
errors=0, trace_dropped=0, raw FSMC observations all zero, last_error=none.
Capture: `build/stm32-disk/after-program-usb.log`. Diagnostic retry is pending;
this does not establish disk operation or resolution of unexpected commands.

Local pinned STM32 dependencies and Python 3.12 live in `build/stm32-tools/`;
paths are in ignored `config/stm32.local.json`. Build using local CMake on PATH
and `PYTHON=.../build/stm32-tools/python-runtime/cpython-3.12.15-linux-x86_64-gnu/bin/python3.12`.
A Python 3.8 relative `__file__` issue in `scripts/stm32_disk.py` was fixed.
Xilinx firmware loaded; JTAG detects XC6SLX9 ID 0x24001093. HP console is
`/dev/ttyUSB4`; STM32 CDC is `/dev/ttyACM0`. ST-Link contact passed.
The older narrative below describes the prior Mac handover state.

## Start here

The user is moving development to a laptop near the HP 2100S so that both
programmers and both serial connections can be used together. At the end of
this session the programmers were elsewhere/disconnected. **Do not assume
devices are connected or a diagnostic has stopped.** Wait for the user to
confirm the new setup before hardware access. No programming was performed
after the diagnostic failures described below.

The next task is to install the already prepared STM32 correction, capture
both serial logs, and find why unsupported disk command values reach the
STM32. Do not treat the emulator as operational merely because the FAT card
mounts, images are READY, or host tests pass.

Latest existing implementation commit at handover preparation:
**`ce393f4` — Updates and bugfix to STM32 firmware**. Check the actual checkout
on the laptop; this handover document may be newer than that commit. The
reference submodule has untracked files on the original machine; inspect them
before cleanup. Do not discard user work or edit the reference submodule as
part of routine port maintenance.

## Purpose and architecture

- Emulate the HP 13210A / HP 7900 disk interface for an initial HP 2100S host.
- Spartan-6 handles HP bus selection, flags, interrupts, status, data buffers,
  and low-level command/data handshakes.
- STM32 handles drive state, seek workers and disk image reads/writes on FAT SD.
- The behavioral reference is `hp2116_verilog/tb_hp2116.sv`, especially
  `stm32_firmware_daemon` and its seek workers. The user reports that the
  reference passes diagnostics and boots RTE II under Verilator.
- Reference submodule baseline is
  `f07b9637157b990d54c7959e7d8c0b1c27f18a61`. It was moved out of requirements
  to the repository top level. Its SystemVerilog is reference material;
  modified Verilog-2001 copies live under `fpga/hp13210/` for ISE 14.7.
- Board clock is 50 MHz; the reference simulation used 100 MHz. The user reports
  a shortest HP bus pulse of 200 ns. Timing equivalence is not yet established.

## Hardware and wiring

| Item | Confirmed details |
| --- | --- |
| FPGA | XC6SLX9, speed grade -2, TQG144; ISE part `xc6slx9-2-tqg144` |
| FPGA clock / LED | 50 MHz P56; active-high LED P143 |
| I/O standard | 3.3 V LVCMOS33 |
| FPGA programmer | Xilinx Platform Cable USB DLC9G clone, xc3sprog `xpc` backend |
| JTAG identity | IDCODE `0x24001093`, XC6SLX9 revision C |
| SPI flash | Winbond W25Q16JVSIQ, 2 MiB, JEDEC `EF 40 15` |
| Flash pins | CS=P38, CLK=P70, flash pin 2/MISO=P65, pin 5/MOSI=P64 |
| Flash boot straps | P60/M1 pulled low; P69/M0 pulled high |
| Other carrier wiring | Flash pins 3 and 7 NC; button connected to FPGA P59 |
| STM32 | DevEBox STM32F4XX-M, STM32F407VET6, 512 KiB flash |
| STM32 clocks / LED | 8 MHz HSE, 168 MHz CPU, 48 MHz USB; active-low PA1 LED |
| STM32 programmer | ST-Link clone over SWD: PA13 SWDIO, PA14 SWCLK, common GND; BOOT0 low |
| STM32 debug USB | Direct USB FS on PA11/PA12, USB CDC output |
| SD socket | SDIO PC8–PC11 data, PC12 clock, PD2 command |
| HP select codes | **Data 14, command 15, both octal** |

Pin workbooks are `requirements/HP 21xx IO bus.xlsx` and
`requirements/STM32F407VET.xlsx`. These and the located FPGA constraints are
the detailed wiring authority. Earlier HP bus P70 assignment conflicted with
flash clock and was corrected; EDT was moved from an output to an unused
receiver. Consult the updated workbook rather than early conversation values.

Both HP receivers and drivers invert; the physical FPGA wrapper compensates
for both. A high driver input is the inactive bus condition. Driver-module
pull-ups to +5 V were removed by the user; planned replacements are 4.7 kΩ
to 3.3 V. **Their installation has not been confirmed in this conversation.**
ACT inputs must not be assumed to have a defined state when floating.
RUN has separate receiver and driver FPGA pins P139/P138 on the same HP bus
signal. General interrupt and DMA request features were deferred; EDT is input.

## What has worked on hardware

1. ISE synthesis, implementation, timing and bitstream generation in Docker.
2. FPGA SRAM programming and visible blink; custom JTAG-to-SPI bridge, flash
   backup/program/readback, and automatic cold boot from flash.
3. Full HP13210 FPGA port programmed into flash. The activity LED gives a
   100 ms pulse for either selected channel; selection resets the idle timer.
   Without activity, the same pulse occurs every two seconds.
4. STM32 programming and two-second LED heartbeat through ST-Link.
5. STM32 USB/FSMC scratch transport test: user photo shows 19 passing loops,
   each 294 patterns and 588 reads, zero failed passes: 5,586 writes and
   11,172 reads. This tests one register; it does **not** prove correct
   switching between register addresses or full disk protocol timing.
6. Disk backend programmed on 2026-10-25. Prepared SD card now mounts on the
   STM32 and all four configured images report READY.

Full hardware disk reads/writes, diagnostic acceptance, and RTE II boot have
**not** passed. Directed FPGA simulation and native backend tests are useful
but do not establish those outcomes.

## Installed versus prepared firmware — critical distinction

| Artifact | State / SHA-256 |
| --- | --- |
| FPGA controller bitstream | SPI flash compared successfully on 2026-10-25; `3f8b76e5db2ea251ce3645cf7540c7ddaf0d7c71052fc543d5a6a788211e0fe6` |
| STM32 disk ELF actually programmed | `775edf788a421f3e4298415433ebea71d96b82c2f5b35b4bb23a84e23e537dc7` |
| Corrected STM32 disk ELF built offline | `c03d0afc193d8c365285d9a3fe3e7da929ca48712fdabd8add7e2ec0057cca34`; **not downloaded** |

ELF hashes identify original-machine builds; a different toolchain/path may
produce a different hash. Keep build receipts and source fingerprints together.
No FPGA HDL change was made in response to the recent failures.

The installed STM32 version mishandles unsupported commands: it sets data-error,
generates attention, and completes the HP command (`??`, `E04`, `CM`). The
reference daemon's default case ignores them. The prepared correction logs
`??`/`E04` but performs no HP status/attention/completion writes. A regression
test verifies this and valid seek completion afterward. **This fixes a real
software difference but does not explain the unsupported command values.**

Prepared firmware also adds retained raw register observations to USB `?`:
`csr`, `request`, `command`, `rar`, and `last_error`. These are latest observations,
not an atomic capture or necessarily the command which caused a retained error.
Reporting does not issue extra destructive CSR reads. Native sanitizer tests
and ARM build pass; latest build used 47,212 bytes flash and 22,696 bytes RAM.

The separate old scratch-test firmware still exists in `firmware/stm32/`.
Its repeated-`t` scheduling bug was fixed offline too; the disk firmware has
no scratch-test loop. Use **stm32-disk** targets for the current work.

## Diagnostic evidence and interpretation

Diagnostic: **DSN 151302**, HP 7900/7901 cartridge disc memory diagnostic.
Original source archive supplied by user:
http://bitsavers.informatik.uni-stuttgart.de/bits/HP/HP_1000_software_collection/master-files/type-4.zip

The archive and extracted `12960-18001_Rev-1805.src` through part 08 are under
ignored `build/reference/hp-diagnostics/`. The diagnostic ABS binary is also
in the reference submodule. Hardware manual:
`requirements/13210-90003_13210A_Disc_Drive_Interface_Kit_May78.pdf`.
Detailed source analysis is in `diagnostics/hp13210/README.md`.

Chronological results:

1. E3 `SFC FAILED WITH FLAG CLEAR-CHANNEL 16`, P=012136, M=012135,
   M DATA=102001, A=3, B=4. **Invalid configuration evidence**: user supplied
   data 15 instead of 14. Idle heartbeat worked but no selection response.
2. Correct data14/command15: E50 `UNIT 0 MISSING-PRESENT NONE`, P=002560,
   A=000000, B=000040, M=002557, M DATA=102006. Expected then: no STM32 disk
   backend, all drives not-ready. Assuming no earlier errors were continued,
   initial flag/selection and command-channel interrupt checks passed, plus
   status/address-record handshakes. No disk transfer was validated.
3. With FAT backend and images: H44 `SEEK IN STEP 02`, E21 `MISSING OR
   DUPLICATE ATTENTION BIT`, H51 cylinder/head/sector/word count zero, unit0.
   Section 1 step1 checks initial status; step2 seeks cylinder0 and checks
   attention. This particular source path scans the rightmost low-four bit,
   so E21 means missing or wrong-unit attention; it does not reject every
   multi-bit pattern. Raw attention value was not captured.
4. Latest run after leaving custom-test entry: H35 `INITIAL STATUS IN STEP 01`,
   E64 `STATUS IS 000003 SHOULD BE 000000`, same zero H51 fields, unit0.
   **HP status bit1=data error, bit0=aggregate error**. This is not drive busy.
   Installed unsupported-command handling can create this status. No evidence
   yet of an SD read failure. This run stopped before the seek test.

STM32 photo before diagnostics showed `commands=136 errors=136 trace_dropped=0`
with HP connected but idle. Subsequent traces show `D3 ?? D3 E04 D3 CM` and
`D0 ?? D0 E04 D0 CM`. `E04` is the STM32 unsupported-command code, unrelated
to HP diagnostic E4. No raw unsupported command word is known yet. Historical
counters do not establish that the HP is still issuing requests while idle.

Diagnostic operator controls checked against source:

- Execution switch-register **bit2**, octal mask `000004`: configuration
  tables/questions. Clear it to leave configuration. H24 displays cylinder
  table 0,1,2,4,8,16,32,64,128,202 **decimal**, valid for this drive.
- H25 WISH TO CHANGE? accepts uppercase `N` (then Enter) to retain a table.
- H62 head mode `C` alternates heads0/1 and2/3.
- Execution **bit3**, octal `000010`: operator-designed custom test. This
  caused H55 ENTER INSTRUCTIONS. Clear bit3, then type `EN` + Enter; source
  checks bit3 after recognizing an opcode and aborts to normal startup.
- Switch register `000000` is suitable for initial standard bring-up and
  halts on errors (bit14 clear). Configuration-time select-code input is a
  different phase; do not leave the select-code value in execution switches.
- Later tests write disk data: use disposable image copies.

Possible further causes, **not established**: FSMC address-switching/read
timing, or command register changing between IRQ acknowledgement and capture.
The FPGA raises a flag during RAR handshake before the firmware's 4 ms seek
attention; the reference HDL has the same behavior. Do not change it solely
on speculation. Reference simulation success remains an important constraint.

## FSMC register interface

16-bit multiplexed asynchronous interface. No NE wire: FPGA internal NE is
held active. NADV=PB7/P75, NOE=PD4/P79, NWE=PD5/P78. Full AD pin mapping is
in the workbook and `firmware/stm32/README.md`. STM32 timing uses ADDSET15,
ADDHLD15, DATAST63, BUSTURN15 at168 MHz for the FPGA's50 MHz sampling.

| AD address | CPU address | Meaning |
| --- | --- | --- |
| 0x00 | 0x60000000 | CSR: bit7 command IRQ, bit6 data IRQ; **read acknowledges command IRQ** |
| 0x02 | 0x60000004 | Command/status: command nibble15:12, drive1:0, seek-aborted5:2 |
| 0x04 | 0x60000008 | Data; access acknowledges data IRQ |
| 0x06 | 0x6000000C | Attention; writes OR low4 bits; even zero write completes an HP command |
| 0x08 | 0x60000010 | Set status: drive15:14 + status mask |
| 0x0A | 0x60000014 | Clear status: drive15:14 + status mask |
| 0x0C | 0x60000018 | RAR: cylinder14:7, head6:5, sector4:0 |
| 0x0E | 0x6000001C | Isolated scratch register |

CPU byte offsets are twice AD addresses. **STM32 SET/CLEAR status packing
differs from the HP returned status word**: STM32 data-error mask is bit0,
busy bit1, etc.; the HP returned word inserts aggregate error at bit0.
CSR output-enable bits8/9 gate physical IRQ pins, not readable raw IRQ flags.
Only low four address bits are decoded; higher addresses alias.

## SD card and backend scope

FAT16/FAT32, `/hp13210.cfg` at root:

```ini
drive0=drive0.img
drive1=drive1.img
drive2=drive2.img
drive3=drive3.img
```

Images are under `/images/`, exactly **4,988,928 bytes** each:
203 cylinders ×4 heads ×24 sectors ×128 little-endian16-bit words.
Offset `(((cylinder*4)+head)*24+sector)*256`. Files opened read/write, not
created or resized. Configuration accepts strict plain filenames, `none` for
offline; see backend README for validation. Reset STM32 to reload configuration.

The user-supplied 8 GB `7900EMU` card was prepared successfully. An initial
macOS mount/fsck problem later disappeared; the proposed format was rejected
and **never performed**. Same volume then passed a read-only filesystem check.
All four images were moved into `/images` without content changes. Original
SHA-256 drive0: `849bb72d0d2cb0966636279920e5795ea77f999d453dcafdc2d040dd64ef1b68`;
drive1/2/3: `404d1e4e239ae179cf1433e43deae10b3b14cc7c753c529799ed25ecf6f63f22`.
Use the saved receipt for authoritative hashes (and rehash if images have
subsequently been written). Do not reuse old `/dev/diskN` assignments on a new
host or reformat this card as routine setup.

Firmware has basic read/write, partial-sector zero-fill, check-data, refine,
4 ms independent seeks, 12 KiB transfer buffer, CSR polling and one pending
command slot. Availability refresh handles HP POPIO resetting not-ready.
Writes sync FAT before completion. Media errors quarantine drives until reset.
Write protection/cylinder metadata are deferred. Exact timing-dependent DMA
overrun diagnostic behavior is deferred by user request. No RTOS, SD DMA,
USB mass-storage or hot-swap support. USB logging is bounded/nonblocking and
drains only when backend idle; `?` reports status, errors and dropped events.

## Laptop environment and transfer

Transfer the checkout including this document, not just an older remote HEAD.
A Git clone does not include ignored `build/`, local config, backups or
downloaded dependencies. Preserve those separately. Never commit proprietary
tool archives, licenses or multi-gigabyte Docker backups merely for migration.

Important ignored evidence/artifacts on the original Mac:

- `build/stm32-disk/programmed.json` versus `success.json`: installed versus
  latest built firmware; `firmware/disk_backend.{elf,bin,hex,map}`.
- `build/stm32-disk/backups/disk-backend-before-e04-fix-20261025/`: original
  disk-backend artifacts and receipts retained before the offline correction.
- `build/stm32-disk/backups/before-disk-backend-20261025T162253304932Z.bin`:
  verified512 KiB old scratch-test flash backup, SHA-256
  `5015ff3643d9773c9e78eb4a04c66a2752997a65a926776c58ead324efb2cddf`.
- `build/controller-board/`: validated bitstream, receipts, flash comparison;
  also preserve original flash backup directories under `build/`.
- `build/reference/hp-diagnostics/`: source archive/extraction and manuals.
- `build/sd-card-inspection/7900EMU-prepared.json`: original image hashes.
- `build/firmware/xusb_emb.hex`: DLC9G RAM firmware, extracted from ISE.
- `config/toolchain.local.json`, `config/board.local.json`, and any
  `config/stm32.local.json`: ignored machine-specific configuration.

Do **not** reuse copied CMake build directories on another path/OS/CPU:
they contain absolute paths and core symlinks. Archive evidence separately,
then create fresh host build directories and reinstall native dependencies.
The laptop OS is not yet confirmed. Scripts were exercised on macOS ARM;
Linux needs native tool packages, device permissions and path configuration.

STM32 builds use STM32duino **2.9.0**, xPack GNU Arm GCC **13.2.1-1.1**,
CMSIS **5.9.0**, CMake >=3.21, Make, Python3 and a native C++ compiler.
OpenOCD **0.12.0-4** was used. On non-Mac hosts configure explicit absolute
`core`, `compiler` (bin directory), `cmsis`, `openocd` paths in
`config/stm32.local.json`; see `firmware/stm32/README.md`. Scripts default to
the Mac's `~/Library/Arduino15/packages` layout, not Linux's Arduino location.
Pinned STM32SD1.5.0/FatFs4.0.4 are fetched by `make stm32-disk-deps` using
`firmware/stm32-disk/dependencies.json` checksums. This retains Arduino library
access with conventional CMake/Make builds rather than Arduino IDE workflows.

ISE runs in amd64 Linux Docker; native host tools handle JTAG. Full image
`hp21xx-ise:14.7` includes ISE; `hp21xx-ise:14.7-runtime` only has dependencies.
The original ignored toolchain config selects full image, license MAC
`08:00:27:68:c9:35`, container license `/opt/Xilinx/Xilinx.lic`. Inspect the
restored image/config before adapting. Without config, the script defaults
to runtime image and will lack vendor tools. Both Docker images are backed up:

- [Image archive](https://drive.google.com/file/d/1t3V-1o7V5462pPJNT_7Uo5Q348tAdit7/view?usp=sharing)
- [SHA256SUMS](https://drive.google.com/file/d/1UmIwX76gUjN4XRSI2xp8G-tPuodl-lwF/view?usp=sharing)

Remote downloads/restoration were not independently tested. Verify checksums,
extract ZIP wrapper if applicable, then `docker image load -i <archive>`.
See `toolchain/README.md` for recovery details. Docker Mac PATH if needed:
`/Applications/Docker.app/Contents/Resources/bin`.

## Suggested continuation sequence

1. Read this file, `diagnostics/hp13210/README.md`, the backend README and
   `requirements/OUTSTANDING_QUESTIONS.md`. Inspect Git status and actual tools.
2. Set up laptop dependencies and clone/initialize the reference submodule if
   missing. Keep original ignored evidence/backups separate from fresh builds.
3. Run offline checks/builds:

   ```sh
   make stm32-doctor
   make stm32-disk-deps
   make stm32-disk-test
   make stm32-disk-build
   ```

4. After user confirms connected/powered setup and HP diagnostic stopped,
   identify ST-Link, Xilinx cable and **both** serial ports. On the previous
   Linux terminal HP was `/dev/ttyUSB0`, STM32 `/dev/ttyACM0`; discover rather
   than assuming these names. Log each separately. Do not send arbitrary
   characters to the HP console as an STM32 probe. Native CDC ignores baud
   for USB transport; recover HP serial settings from the user's working setup.
5. Program corrected backend using **`make stm32-disk-program`**. This validates
   build fingerprints, backs up/verifies512 KiB flash, then programs/verifies
   and resets. Do not use `make stm32-program` (old scratch test).
6. FPGA flash already matched current HDL; no planned FPGA rewrite. If comparison
   is needed, `python3 scripts/verify_controller_flash.py` temporarily loads
   the SPI bridge and finally reloads existing flash. **Halt/stop STM32 first**
   because the temporary bridge removes the FSMC endpoint. It requires local
   validated controller/bridge builds and native xc3sprog. Do not casually run
   `make flash-program`, which refers to the blink image.
7. For DLC9G cold USB ID `03fd:000d`, initialize with
   `make cable-firmware CABLE_FIRMWARE=build/firmware/xusb_emb.hex`; it should
   re-enumerate as `03fd:0008`. `make jtag-detect` checks chain. Firmware is RAM
   resident and may need loading after disconnect. macOS `make usb-scan` is
   platform-specific; Linux needs its own enumeration/permissions.
8. With corrected firmware and disposable images, reset boards, get STM32 `?`
   output, then another after a few idle seconds. Record raw registers/counter
   changes. Re-run DSN151302 with data14/command15 octal and execution switches0.
   Capture first failure and nearby STM32 trace. If E04 persists, use raw command
   nibble/drive/RAR and IRQ state to distinguish register/timing problems from
   supported commands. Do not claim corrected unsupported handling solved the
   underlying transport problem without this evidence.
9. Once capture/seek works, validate real sector reads/writes against disposable
   host image bytes; then broader diagnostics/RTE II. Keep DMA-overrun timing
   and write protection out of this first repair unless new evidence requires it.

Other useful offline targets: `make test` (HDL and Python checks),
`make flag-diagnostics` (small standalone14/15 HP flag programs),
`make controller-build` (full ISE bitstream, no programming). Latest previous
full HDL regression passed14 controller variants plus board/activity cases;
recent changes are STM32-only and its sanitizer tests/build pass.

Suggested first message to the laptop agent:

> Read HANDOVER.md and continue HP13210 bring-up from that state. Check the
> checkout and toolchain first. The prepared STM32 unsupported-command fix has
> not been downloaded; the installed version produced E04 and HP E21/E64.
> Confirm my current connections before accessing hardware, then capture both
> serial logs and install/test the prepared firmware.
