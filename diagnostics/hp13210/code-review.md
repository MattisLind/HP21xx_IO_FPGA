# FPGA and STM32 review — 2026-10-29

Reviewed baseline: `fpga-rework-experimental`, commit `32ed30c` ("Experimental
also works"). The saved HP console contains two complete long passes with zero
errors, unit 00, heads 0/1; the user confirmed this version worked. This is
evidence for that diagnostic configuration, not exhaustive coverage of every
drive, cancellation sequence, or storage failure.

This review did not access or program hardware. Production RTL and firmware
are unchanged. Isolated experiments and receipts are under `build/code-review/`.

## Recommended order

1. Remove the hidden USB connection-check delay as a standalone firmware
   experiment. It is the clearest useful performance improvement.
2. Make small, behavior-preserving cleanups: remove redundant read-wait state,
   redundant configuration validation, unused RTL, and repeated attention-bit
   assignments. Keep these separate from behavior corrections.
3. Correct the two reproduced FPGA attention/reset corner cases, each with a
   permanent regression and explicit reference-behavior checks.
4. Join the actual C++ backend to the RTL in a regression before changing
   request ownership or removing the software pending slot.
5. Bound storage-driver readiness waits and test the error path with injected
   card failures.

There is no evidence that raising clocks or shortening bus timing is currently
worth the risk. The existing FPGA meets 50 MHz comfortably; synthesis already
removes much of the apparent redundant source logic.

## Confirmed tuning opportunity: USB checks stall idle polling

[`main.cpp:158`](../../firmware/stm32-disk/src/main.cpp#L158) uses
`const bool current=bool(Serial);` after each idle backend step. In the pinned
STM32duino 2.9.0 library, `USBSerial::operator bool()` calls `delay(10)` before
returning `dtrState`. `USBSerial::dtr()` returns the same state directly.

The installed-image ELF, SHA-256
`f006ce156f847832dc0579f44e8468944e20016752aeaf51f87d0a97e11aae8e`, confirms
this is real compiled behavior: `loop()` calls the conversion function, which
loads 10 and calls `delay`. Every idle loop can therefore leave a newly arriving
command unserviced for approximately 10 ms, with or without a terminal attached.
The active transfer path returns before this code, so this does not explain a
10 ms pause between each streamed data word.

Proposed change: `const bool current=Serial.dtr();`.

An isolated host harness compiled the actual `main.cpp` with peripheral stubs,
then a copy with only this substitution. Disconnection, connection, `?`,
reconnection, and restricted USB transmit space produced identical 1,740 output
bytes and three status reports. Across 720 idle calls, the original requested
7.2 seconds of artificial delay; the candidate requested none. ASan/UBSan passed.
These are stubbed-loop results, not measured hardware throughput.

Evidence: `platform-elf-results.json`, `platform-{built,ready}-usb-disassembly.txt`,
`check-platform-loop.py`, and `platform-loop-results.json` in `build/code-review/`.
The candidate still needs an ARM build and a physical diagnostic run. Removing
the delay changes command-service timing, so treat it as its own experiment.

## Confirmed FPGA corner cases

### Unrelated device I/O can erase disk attention

At [`hp13210a_core.v:371`](../../fpga/hp13210/hp13210a_core.v#L371),
`seek_record_command` and `status_check_command` combine the retained opcode
with global `ioo`, without checking this card's select code. These signals clear
all attention bits at line 724.

The isolated test writes attention `0005`, leaves either STATUS or SEEK selected
in the command register, and pulses IOO with neither disk channel selected.
Both cases read back `0000`. A command to an unrelated device should not consume
this controller's attention. This can matter in a running OS even though the
disk-only diagnostic passes.

This decode is inherited from the original Verilog model, not introduced by
the mailbox conversion. Matching that model alone would miss it. Before fixing,
check selected command/data-channel behavior against the interface manual;
blindly adding `csel` may change intentional address-word behavior. Preserve
the current priority between attention clearing and simultaneous MCU writes.

### CRS can leave the address handshake stuck

The first SEEK address word sets `reset_data_channel_encode_ff`. In
`SEEK_STORED_DATA`, CRS returns the FSM to IDLE without clearing that flag
([core lines 598–611](../../fpga/hp13210/hp13210a_core.v#L598)). The flag then
continually clears the data encode flip-flop at line 578.

The isolated test asserts CRS while the first-word acknowledgment is active,
then sends a complete new SEEK. After CRS the state is IDLE with acknowledgment
still asserted; the new seek remains in state 1 and CSR is `0040`, without a
command request. Recovery currently needs a stronger reset. This behavior also
exists in the original model.

Fix the handshake's CRS recovery explicitly and test CRS in every address FSM
state, including its relation to STC/CLF. Preserve already accepted mechanical
seeks; resetting an incomplete address handshake must not cancel those workers.

Both findings were reproduced with the actual current core and wrapper, using
the existing testbench's bus drivers. Run:

```sh
python3 build/code-review/run-fpga-review-corners.py
```

`build/code-review/fpga-corners/results.json` records sources, commands, and three
expected assertion failures. This Icarus version returns zero even after
`$fatal`, so inspect the recorded output, not just the exit status. These tests
are review reproductions, not additions to the passing release suite.

## Firmware request ownership needs a joined test

[`Backend::poll()`](../../firmware/stm32-disk/src/backend.cpp#L181) always reads
CSR, which consumes a hardware request. If the software pending slot is already
occupied, it still reads COMMAND/RAR, reports E09/Overrun, and drops that packet.
The slot can remain occupied while a read waits for its drive's seek to finish
(lines 232–238). The hardware accepts drive seeks independently and asserts
Busy before the backend starts their workers.

An isolated native reproducer exercises this ordering:

1. SEEK drive 0 is dispatched and positioning continues.
2. A READ for drive 0 is captured and waits for that positioning operation.
3. The host cancels the ordinary command and accepts a SEEK on drive 1.
4. The next firmware poll consumes and drops SEEK 1 because its pending slot
   still contains READ 0. No drive-1 worker exists to clear its Busy state.

`build/code-review/pending-cancel-reproducer.cpp` reproduces E09 and retained
drive-1 Busy/Seeking in the C++ bus model. It explicitly models FPGA Busy and
the absence of a cancellation notification for a packet already taken by the
MCU. **This is not yet an end-to-end RTL/firmware reproduction or an observed
hardware failure.** Completing an already captured data operation after CLC may
itself be intentional sector cleanup; the dropped seek is the concern.

The current native suite deliberately expects E09 for a second pending request
([test lines 630–634](../../tests/stm32/backend_test.cpp#L630)), so a passing suite
does not establish that every legal cancellation/reissue sequence is lossless.
The HP CPU/RTE simulations execute `stm32_firmware_daemon` and
`stm32_seek_worker` in `hp2116_verilog/tb_hp2116.sv`, not this C++ implementation.

Do not add another general FIFO to hide this. First connect production
`hp::Backend` to the real RTL using a simulated `Bus`, clock, and image store.
Exercise delayed polling, four accepted seeks, CLC/reissue, and seek completion
during data operations. A future protocol could separate non-destructive status
polling from explicit request acceptance, so hardware retains packets until the
MCU can accept them. That would require a coordinated protocol change and clear
cancellation semantics, rather than merely deleting `pending_`.

Likewise, dispatching a seek immediately from `poll()` is not a safe local fix:
`dispatch()` overwrites the selected drive, command, address, and other context
of the active operation. Independent seek acceptance would need its own local
context first.

## Storage errors can wait forever below the backend

The pinned FatFs adapter has unbounded loops waiting for
`BSP_SD_GetCardState()==MSD_OK` after successful block reads and writes:

* `build/stm32-disk/deps/FatFs/src/drivers/sd_diskio.c:129,155`
* `build/stm32-disk/deps/STM32SD/src/bsp_sd.c:712` maps every non-TRANSFER card
  state to BUSY.

The configured transfer timeout does not bound these later loops. A card that
never returns to ready can stall the entire backend rather than returning an
error to its existing quarantine/completion path. This is confirmed from the
pinned source; no physical card failure was induced during review.

Use a tracked driver override or reproducible patch with a wrap-safe readiness
deadline and an error return. Test prolonged BUSY, state-query failure, timer
rollover, and recovery/quarantine. Do not edit only downloaded dependencies:
such a fix would disappear on the next clean dependency fetch. Native backend
tests currently do not compile `FatImages`, FatFs, or this driver.

## Small simplifications with bounded scope

| Candidate | Why it is justified | Expected benefit / check |
| --- | --- | --- |
| Remove `read_wait_`; test `position_ != 0` in the shared READ/CHECK path | The flag is false before the first word, then true whenever a word is staged. Clearing it before staging the next word never survives the current call. Dispatch resets position. | One less state variable/invariant; full native suite passed on an isolated copy. No size/speed claim yet. |
| Remove the first exact-case duplicate-image loop in `config.cpp:47` | The following loop checks all drives case-insensitively, including out-of-order keys, and subsumes it. | Less duplicated validation; retain existing duplicate-name tests. |
| Remove unused core declarations and decode chains | Includes the unused CSR falling-edge path, command-status write pipeline, attention read decode, drive-select helpers, constant helper signals, and duplicate `drive_busy` term in `any_error`. | Clearer RTL; synthesis already discards these, so expect little area improvement. Keep the CSR read-start register and DATA/attention completion pipelines. |
| Vectorize the four attention-bit updates | Each bit uses exactly the same clear condition, then ORs its corresponding MCU input bit. | Replace four identical chains with one vector operation, retaining clear-before-write priority. Do not combine with the attention decode fix. |
| Use named command and CSR masks | Repeated command numbers and `0x40`/`0x80` obscure protocol review. | Readability, no intended timing or protocol change. |
| Cache the idle LED output before calling `digitalWrite` | The same level is repeatedly written on every idle iteration. | Small idle-loop saving after the USB delay is removed; preserve active/heartbeat transitions. |

The `read_wait_` experiment, diff, and test evidence are under
`build/code-review/no-read-wait/`. It has not been applied to production.

Avoid compressing the READ, CHECK, drain, and write-boundary states into a
generic transfer state. Their differences implement diagnostic-visible rules:
autonomous CHECK completion, late-word rejection, partial-sector closing, and
EOC only after an extra write request. Fewer enum values would not necessarily
mean a simpler or more reliable implementation.

## Preserve these established constraints

* Keep the 4 MHz SDIO setting. The earlier 24 MHz polling implementation had a
  physically captured TX FIFO underrun; DMA would be a separate project.
* Keep `f_sync` before write completion, range checking, and drive quarantine.
* Keep the measured FSMC address/read/write qualifiers and per-access `__DSB()`.
  Shortening waits or removing pipeline stages requires new waveform evidence.
* Keep atomic CSR packet capture and live seek-abort visibility.
* Keep independent drive positioning after interface cancellation.
* Keep trace buffering out of per-word USB transmission; preserve long filenames
  and the testable `Bus`/`Images` interfaces.

The reviewed bitstream's 7.435 ns minimum period meets its 20 ns internal clock
constraint. That number does not prove asynchronous bus setup/hold margins or
justify raising the board clock.

## Validation performed for this review

* Current production native backend/configuration suite: PASS under ASan/UBSan
  and LeakSanitizer, rerun outside the ptrace sandbox.
* Isolated removal of `read_wait_`: full native suite PASS under ASan/UBSan.
* Actual-main-loop USB comparison: identical output, hidden delay removed in
  the stubbed candidate; ASan/UBSan PASS.
* Current FPGA: three focused tests reproduce the two attention/reset issues.
* Native pending-command reproducer: confirms packet-drop behavior under its
  explicitly modeled bus/cancellation assumptions.
* Installed firmware ELF inspected offline; no debugger, serial write, reset,
  programming, or physical storage operation used.

The isolated sandbox runs disable leak detection because LeakSanitizer cannot
operate under ptrace; the unchanged baseline suite was also run with leak
detection outside that sandbox. No candidate is represented as hardware-tested.
