# STM32 HP13210 disk backend

This is a separate firmware image for the STM32F407VET6 carrier. It ports the
backend in `hp2116_verilog/tb_hp2116.sv` to polling firmware with FAT-backed
disk images. It has been compiled and tested on the host; **hardware disk
operation remains unverified**. Programming outcomes and remaining hardware
checks are recorded in [outstanding questions](../../requirements/OUTSTANDING_QUESTIONS.md).
The existing [USB/FSMC transport test](../stm32/README.md) remains available;
the user confirmed 19 consecutive passing iterations on 2026-10-25.

The HP diagnostic with data select code **14**, command **15** (octal) reached
E50 because no drive was ready. This backend marks successfully opened images
ready and services the disk commands; it does not establish that the whole
controller now passes diagnostics. The observed E50 is consistent with the
current bring-up stage, not full hardware acceptance.

## SD card layout

Use a FAT16 or FAT32 card in the carrier's SDIO socket. Copy the example
[hp13210.cfg](sd-card/hp13210.cfg) to the root and place images in `/images`:

```text
/hp13210.cfg
/images/drive0.img
/images/rte.img
```

```ini
# Filenames are relative to /images; comments occupy their own lines.
drive0=drive0.img
drive1=rte.img
drive2=none
drive3=none
```

Keys are `drive0` through `drive3`. Missing keys, empty values and `none` mean
offline. Values are unquoted filenames, up to 63 ASCII letters/digits/dots/
underscores/hyphens, without directory components. Duplicate keys, unknown
keys, duplicate image names (case insensitive), or malformed configuration
leave all drives offline. The configuration file is limited to 1024 bytes.
Edit it on the host and reset the STM32 to reload; there is no hot-swap or
USB mass-storage mode.

Each raw image must be exactly **4,988,928 bytes**:
203 cylinders × 4 heads × 24 sectors × 128 16-bit words. Word bytes are
**little endian**, matching the testbench; sectors are ordered by cylinder,
then head, then sector. There are no file headers. The byte offset is:

```text
(((cylinder * 4) + head) * 24 + sector) * 256
```

To create a new blank image on your host without replacing an existing file:

```sh
python3 - <<'PY'
with open('drive0.img', 'xb') as image:
    image.truncate(203 * 4 * 24 * 256)
PY
```

Copy that file to the card's `images` directory. Existing testbench images
with this layout can be used directly. A blank image contains no bootable OS.
Configured images are opened read/write without creating, truncating, or
appending. Missing, wrong-sized, or inaccessible images remain offline.
Write protection and cylinder-attribute metadata are deferred. Successful
writes are synchronized to FAT before command completion; this is not an
atomic or power-loss-protected disk store.

## Build and tests

```sh
make stm32-disk-deps   # Explicit network fetch of checksum-pinned libraries.
make stm32-disk-test   # Host C++ tests with address/undefined-behavior sanitizers.
make stm32-disk-build # Native ARM compiler / CMake-generated Makefiles.
```

STM32duino 2.9.0, the GNU Arm compiler, and CMSIS are detected using the same
installed dependencies as the transport test. The new helper uses its own
`build/stm32-disk/` directory. It does not overwrite `build/stm32/firmware/` or
the transport test's build/program receipts. `make stm32-build` and
`make stm32-program` still refer to the old transport test, not this backend.
To install this separate image after transport bring-up, explicitly run:

```sh
make stm32-disk-program
```

This checks the successful-build fingerprints, saves and verifies a fresh
512 KiB STM32 flash backup under `build/stm32-disk/backups/`, then programs,
verifies and resets the processor through ST-Link. The receipt is
`build/stm32-disk/programmed.json`. Build/test commands do not program devices.

The SDIO/FAT libraries are
[STM32SD 1.5.0](https://github.com/stm32duino/STM32SD/tree/9b9bf7053c1d5b61758bd2fa415669233a7f1229)
and [FatFs 4.0.4](https://github.com/stm32duino/FatFs/tree/cef1acad37d563e6b7dfd1c4fd3d48e7ff348947).
[dependencies.json](dependencies.json) pins commits and archive SHA-256 hashes.
Sources and their licenses are downloaded under `build/stm32-disk/deps/`,
not vendored into the repository. The build records source/dependency hashes
and the ELF checksum in `build/stm32-disk/success.json`.

Outputs are `build/stm32-disk/firmware/disk_backend.{elf,bin,hex,map}`.
The board uses its 8 MHz HSE, 168 MHz CPU, 48 MHz USB, and the same conservative
FSMC setup as the old test. SDIO is explicitly PC8–PC11 (D0–D3), PC12 (clock),
PD2 (command), with no card-detect input. SDIO uses the library's blocking
HAL transport; no SD DMA or RTOS is required.

When eventually loaded, the backend starts automatically without USB/DTR.
USB CDC sends status on connection or `?`, only while the backend is idle.
PA1 has the two-second idle heartbeat and lights during active work. The old
transport test's `t`/`s` commands belong to that separate firmware.

## Short USB operation trace

Tracing is enabled by default in the disk-backend firmware. Each record is
one short code followed by CR/LF. `D0`–`D3` identify the drive for the following
operation or result. Drive markers are repeated for results so overlapping
seek workers cannot make a completion look as though it belongs to another
drive. For example, a short write to drive 0 can produce:

```text
D0
WR
D0
TO
D0
ZF
D0
CM
```

This means write started, the normal word-gap timeout ended the transfer,
the remainder of the partial sector was zero-filled, and completion was
signalled. `TO` is not itself a fault: short DMA transfers normally end this
way. `CM` means the backend took its completion path, including on an error;
check for preceding `E` codes rather than interpreting it as proof of success.
Unsupported commands are logged as `??`/`E04` and ignored without status,
attention or completion writes, matching the reference testbench. The initially
programmed firmware incorrectly completed these requests; the correction is
prepared offline and has not yet been downloaded.

| Code | Meaning |
| --- | --- |
| `BT` | STM32 backend boot |
| `SD`, `CF` | SD/FAT mounted; configuration parsed |
| `R0`–`R3`, `N0`–`N3` | Drive ready or offline at backend startup |
| `D0`–`D3` | Drive context for an operation/result |
| `WR`, `RD`, `SK` | Write, read, seek dispatched |
| `RF`, `CK`, `IN` | Refine sector, check data, initialize data dispatched |
| `AR` | Address-record request observed by the backend, if forwarded |
| `??` | Unrecognized command observed |
| `CM` | Command completion path taken |
| `SC`, `SA` | Seek completed, or attention suppressed by the FPGA's seek-aborted latch |
| `TO`, `ZF`, `EC` | Word-gap timeout, partial-sector zero-fill, end of two-head cylinder |

These records describe the STM32's view. Normal status and address-record
operations are handled inside the FPGA and do not generate a backend command
request, so they cannot normally be traced by this firmware. No per-word
records or periodic availability-refresh records are emitted.

The error numbers below are **STM32 trace codes**, separate from the HP
diagnostic's E codes. Runtime errors also increment the backend's `errors`
counter; startup/configuration errors are reported by their codes and the
status message.

| Code | Meaning |
| --- | --- |
| `E01` | Command addressed an offline or quarantined drive |
| `E02` | Seek requested while that drive was already seeking |
| `E03` | Invalid seek cylinder/head/sector |
| `E04` | Unsupported command; ignored without HP completion or attention |
| `E05` | Invalid transfer cylinder/head/sector |
| `E06` | Requested cylinder differs from the drive's current cylinder; write/init exits, reference-style read/check may continue |
| `E07` | Image read failed; drive quarantined |
| `E08` | Image write or FAT synchronization failed; drive quarantined |
| `E09` | Pending-command slot already occupied; additional command dropped |
| `E10` | Check-data sector count did not arrive before timeout |
| `E11` | SD/FAT mount failed |
| `E12` | Cannot open `/hp13210.cfg` |
| `E13` | Configuration read/close failed or file exceeds 1024 bytes |
| `E14` | Malformed configuration, including embedded NUL |
| `E15` | Cannot open the configured image read/write; preceding `D` identifies it |
| `E16` | Wrong image size; preceding `D` identifies it |
| `E99` | Trace buffer overflow: some records were dropped |

The engine only enqueues byte-sized events into a fixed 1024-record RAM ring.
It never prints or waits for USB. The main loop drains complete lines using
available transmit-buffer space only while the backend is idle. Long status
reports and partially transmitted trace lines are kept separate. Connecting
USB later drains retained startup/history records; a disconnected or slow
terminal cannot block disk handshakes. Under sustained activity the ring can
fill: new records are dropped, retained records stay in order, and a single
`E99` is emitted after the queue drains. The `?` status report includes the
cumulative `trace_dropped` count. Trace buffering is diagnostic assistance,
not a lossless log or a measurement of physical bus timing.

The updated `?` report also prints hexadecimal FSMC register diagnostics:
`csr` is the most recent CSR poll; `request` is the most recent CSR with command
IRQ set; `command` and `rar` are the raw words for the last dispatched request.
`last_error` retains the latest runtime error code, or `none`. These are retained
observations, not an atomic bus capture: later activity may replace the command
words after an error. Status reports do not perform extra FSMC reads, since a
CSR read acknowledges command IRQ. Capture the report promptly after a failure.

## Testbench correspondence

| Testbench behavior | Firmware implementation |
| --- | --- |
| `stm32_firmware_daemon` | `Backend::step()` polls CSR bits 7/6 instead of relying on unwired IRQ/DRQ pins. |
| Command acknowledgement | Every CSR read acknowledges command IRQ; command and RAR are captured immediately, including during an active transfer. One pending command is retained. |
| Status/attention registers | Same AD register addresses, status masks, drive bits 15:14 and attention bits 3:0. CPU byte offsets are twice the AD addresses. |
| `stm32_seek_worker` | Independent per-drive 4 ms deadlines; busy/seeking clear on completion, and the FPGA seek-aborted latch suppresses attention. |
| READ DATA (`2`) | Preload the rest of the current two-head cylinder into RAM; present one little-endian word at a time using the DATA/CSR handshake. |
| WRITE DATA (`1`) | Collect words in RAM; zero-fill the rest of a partially written sector after transfer timeout; write completed sectors and synchronize before attention. |
| INITIALIZE DATA (`9`) | Same basic write path and zero-valued attention completion; cylinder attributes/protection are not implemented yet. |
| CHECK DATA (`6`) | Read the sector count, clock zero words as in the model, and track the cylinder boundary. No magnetic media/CRC fault simulation. |
| REFINE SECTOR (`5`) | Complete using a zero-valued attention write, as in the model. |
| ADDRESS RECORD (`B`) and status (`0`) | RAR capture and status-word generation remain in the existing FPGA. |
| Data ending at head 2 or head 0 | Stop at the same two-head boundary; never access outside the image or consume the reference write loop's extra word after EOC. |

At startup, valid images clear not-ready and set first-status. Missing images
remain not-ready. The firmware republishes availability every 10 ms while no
data transfer is active, because HP POPIO resets the FPGA's status vector too.
An image I/O error sets data-error/unsafe/not-ready and quarantines that drive
until STM32 reset. It is not automatically brought back online by this refresh.

A 12 KiB buffer holds the remaining part of a two-head cylinder. SD reads occur
before a read stream; writes and `f_sync` occur after collecting a write stream.
There are no FAT or USB calls during individual word handshakes. This avoids
per-sector SD latency within a transfer, but initial read latency and final
write latency still depend on the card. Image geometry/ranges are checked.

The initial word-gap timeout is **100 microseconds**, deliberately more lenient
than the simulation's sub-microsecond waits. It ends short transfers but is
not the cycle-accurate DMA-overrun mechanism. The diagnostic's specially timed
overrun case may fail; the reference's delayed 3 µs overrun probe has not been
reproduced. Filesystem latency, polling throughput and FSMC timing must be
measured before tightening this. The backend retains only one pending command;
a further command arriving before it is serviced reports overrun.

## Verification and next hardware checks

Host tests cover configuration errors and mapping, image geometry/byte order,
ready/offline startup, POPIO availability refresh, independent seeks and abort,
timer rollover, read/write handshakes, partial-sector filling, preservation of
following sectors, final-image boundaries, media failures/quarantine, pending
commands and check-data. Sanitizers check the same C++ engine compiled for the
STM32, using a mock register bus and in-memory images. These tests do not model
physical FPGA timing or exercise the actual SD socket/FAT driver on hardware.

Trace tests additionally cover event ordering, drive context across concurrent
seeks, runtime error codes E01–E10, normal timeout versus failure, ring
wraparound, overflow reporting and dropped-record accounting.

First run the already installed USB/FSMC transport test and confirm repeated
passes. Then test SD mounting and drive mapping with the new image, followed
by non-destructive reads and writes to a disposable disk image. Compare readback
bytes on the host, then rerun the HP diagnostic. Physical tests, RTE II boot,
precise overrun behavior and write protection remain outstanding.
