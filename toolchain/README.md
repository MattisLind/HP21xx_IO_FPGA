# ISE 14.7 toolchain and bring-up

The project uses ISE 14.7 inside a Linux x86-64 Docker image and native macOS
tools for simulation and JTAG. The Spartan-6 CLI tools have been extracted from
the supplied vendor VM archive and packaged as `hp21xx-ise:14.7`. The DLC9G
clone has been initialized successfully and detects the connected XC6SLX9.
The reported FPGA marking includes `2C`: speed grade -2, commercial temperature
range. ISE uses part `xc6slx9-2-tqg144`.

## Current status, 2026-10-16

| Check | Result |
| --- | --- |
| Docker client/server | Working: Docker 29.8.2, Docker Desktop 4.94.0. |
| Runtime image | `hp21xx-ise:14.7-runtime`, 133 MB, Ubuntu 20.04 with 64-bit runtime dependencies and Python 3.8; no vendor files. |
| ISE image | `hp21xx-ise:14.7`, containing the Spartan-6 CLI tools and the supplied VM license. |
| x86 execution on this ARM Mac | Passed: `uname -m` is `x86_64`, Debian package architecture is `amd64`, Python and Make execute. |
| Host/container project sharing | Passed: container-created output is visible on the host. |
| Blink simulation | Passed using Icarus Verilog 13.0: startup, divider boundaries, both LED polarities, and a one-clock half-period. |
| Native programmers | Built ARM64 `xc3sprog` with the `xpc` backend and libusb's `fxload` RAM loader. Installed openFPGALoader 1.1.1 as an alternative for supported cables. |
| ISE executable check | Passed: XST, NGDBuild, MAP, PAR, TRACE, and BitGen are available; XST reports release 14.7. |
| Implementation and timing | Synthesis, translation, mapping, routing, and TRACE passed at 20 ns; minimum period 4.110 ns, worst setup slack 15.890 ns, zero timing errors. |
| BitGen no-bitfile check | Passed using `-j` and output `blink.drc`: zero DRC errors/warnings and no `.bit` file generated. |
| Connected cable | Firmware RAM upload passed: `03fd:000d` changed to `03fd:0008` with product name `XILINX`. |
| Target detection | Passed through the DLC9G clone: JTAG position 0, IDCODE `0x24001093`, XC6SLX9 revision C, instruction register length 6. |
| Hardware blink build | Passed for `xc6slx9-2-tqg144`, clock P56 at 50 MHz, LED P143, LVCMOS33. Minimum period 3.973 ns, setup slack 16.027 ns, hold slack 0.447 ns; zero timing errors and zero BitGen DRC errors/warnings. |
| SRAM download and physical blink | Passed: `make program` completed with exit status 0 through the DLC9G clone, and the user confirmed that the LED blinks. First hardware blink milestone complete. |
| SPI flash | Carrier bridge built; Winbond `EF 40 15` identified, 2 MiB backup verified, blink boot image programmed and verified twice. User confirmed blinking after power cycling without a download on 2026-10-17. Automatic flash boot verified. |
| Build validation | Sixteen tests pass, including located pin-map/stale-image checks, timing/board validation, and flash identity, QE, and protection checks. All HDL simulation modes also pass. |
| HP13210 full-port smoke, 2026-10-17 | Both simulation modes and full ISE smoke build pass: 129 slices, 250 flip-flops, 314 LUTs; 5.635 ns minimum period and zero timing errors at 50 MHz; no-bitfile DRC has zero errors/warnings. |
| HP13210 FPGA-only carrier image | All pins located; 42 slices, 103 flip-flops, 94 LUTs; minimum period 3.822 ns, zero timing/DRC errors. Previous flash backed up and verified; controller programmed and verified twice. User confirmed its 2 Hz heartbeat after power cycling; cold boot verified. |

Evidence is under `build/toolchain/`, `build/tools/`, `build/sim/`, and
`build/smoke/`. Target-device detection and physical programming are separate
from the software smoke test.

The verified image ID is
`sha256:27aac6d75e149603e7c609cad575ccd68781ea0f73fce6b259946f08192badad`.
`build/smoke/success.json` records the successful software verification.
The initial BitGen invocation used the wrong output extension; after correcting
it to `.drc`, only BitGen was rerun against the verified routed design. Its
successful output is in `bitgen-retry-container.log`, and the receipt preserves
both source fingerprints. Subsequent `make smoke` runs use the corrected name.

## Docker image recovery backup — Google Drive

Backup links supplied by the user on **2026-10-24**, for recovery if the local
Docker cache is lost or purged:

| File | Download link |
| --- | --- |
| Docker image archive (described by the user as a ZIP archive) | [Google Drive image backup](https://drive.google.com/file/d/1t3V-1o7V5462pPJNT_7Uo5Q348tAdit7/view?usp=sharing) |
| SHA-256 checksums | [Google Drive SHA256SUMS](https://drive.google.com/file/d/1UmIwX76gUjN4XRSI2xp8G-tPuodl-lwF/view?usp=sharing) |

The intended backup contains both `hp21xx-ise:14.7` (complete ISE toolchain)
and `hp21xx-ise:14.7-runtime` (runtime dependencies only). These links were
recorded as supplied; the remote files have not been downloaded, their hashes
have not been independently verified, and restoration has not yet been tested.

To recover:

1. Download both files, retaining their original filenames. Inspect
   `SHA256SUMS` to identify the filename it covers.
2. In the directory containing that file and `SHA256SUMS`, verify it:

   ```sh
   shasum -a 256 -c SHA256SUMS
   ```

3. Start Docker Desktop. If the download is an actual ZIP wrapper, extract it
   to obtain the Docker image tar archive. Docker can load a tar or compressed
   tar directly; substitute its actual filename below:

   ```sh
   docker image load -i <docker-image-archive.tar-or-tar.gz>
   docker image ls hp21xx-ise
   ```

4. Confirm that tags `14.7` and `14.7-runtime` are present. From the repository
   root, run `make runtime-check` and `make toolchain-check` to check the
   restored environment without programming hardware.

On this Mac, if `docker` is missing from PATH, use:

```sh
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

Keep the repository and any local configuration backed up separately; an
image archive does not include host-mounted project files.

## Commands available now

From the repository root:

```sh
make help
make sim
make test
make runtime-image
make runtime-check
make doctor
make toolchain-check
make smoke
```

The driver reads the generated `config/toolchain.local.json`, so normal build
commands select the provisioned image without additional environment setup.
Explicit environment variables override those local defaults. The driver
finds Docker inside `/Applications/Docker.app` if absent from `PATH`, including
its credential helper. Builds explicitly request `linux/amd64`, run all ISE
stages in one container, mount the repository at `/work`, and write artifacts
under `build/`.

The [runtime Dockerfile](Dockerfile) installs dependencies. The
[ISE Dockerfile](Dockerfile.ise) adds the extracted tools and license. Vendor
files, generated settings, and the archive are ignored by Git. The reference
submodule is unchanged.

## Provision ISE

Place `Xilinx_ISE_14.7_Win10_14.7_VM_0213_1.zip` in the repository root. The
archive is available through [AMD legacy ISE downloads](https://www.xilinx.com/support/download/index.html/content/xilinx/en/downloadNav/vivado-design-tools/archive-ise.html).
Its verified MD5 is `085a59d7e0e33f03eaae730c25f22bd4`.

To reproduce the setup on Apple Silicon:

```sh
# Extraction host: Python 3.10 or newer.
python3 -m pip install --target build/tools/python -r toolchain/extract-requirements.txt
make runtime-image
make provision-ise
make ise-image
make toolchain-check
make smoke
```

[provision_ise.py](../scripts/provision_ise.py) verifies the archive, streams the
compressed VMDK out of the ZIP/OVA, and reads its Linux filesystem directly
using Dissect. It never boots the VM or expands its roughly 60 GiB filesystem
into a raw disk. The compressed VMDK takes about 15.7 GiB; selected tool files
take about 2.0 GiB. Allow additional space for Docker layers and build context;
roughly 25 GiB free in addition to the ZIP is a useful provisioning allowance.

The selected installation includes 64-bit CLI binaries/libraries, common data,
Spartan-6 device data, and HDL libraries. It omits EDK, PlanAhead, SysGen,
other device families, and 32-bit binaries. This is a Spartan-6 CLI image,
not the complete GUI suite. The [original Docker approach](https://github.com/vmunoz82/ise14)
extracts the broader installation and reports substantially higher disk use.

The original VM license is copied unchanged. The runner preserves its VM
adapter MAC `08:00:27:68:c9:35`. License-bearing ISE runs use Docker's bridge
network so the adapter exists; dependency-only runtime checks use network
`none`. The image also installs the license in the standard root-user Xilinx
license directory. The tools may emit legacy subscription warnings; build
exit status and implementation/timing reports determine the test result.

`build/ise/provision.json` records the selection and archive checksum. The
provisioning script first configures a read-only installation mount. The
image build then updates `config/toolchain.local.json` to use the complete
project image and its internal license path. Both modes remain available:

- `ISE_INSTALL_DIR` names a Linux `ISE_DS` installation; `ISE_LICENSE_FILE`
  names its host-side license. These mounts are read-only.
- `ISE_IMAGE` selects another Linux amd64 image containing Bash, Python 3.8+,
  and ISE. `ISE_CONTAINER_LICENSE_FILE` selects a license inside that image.
- `ISE_SETTINGS` overrides the container's `settings64.sh` path.
- `ISE_LICENSE_MAC` supplies the MAC associated with that licensed installation.

The vendor ZIP, intermediate VMDK, extracted tools, license, and local settings
remain outside Git. Keep the supplied archive to reproduce the installation.

## Implementation stages

The flow follows the [ISE 14.7 Command Line Tools User Guide, UG628](https://docs.amd.com/v/u/en-US/devref).
Use Verilog-2001 for synthesis; the simulation testbench may use SystemVerilog.

| Stage | Tool | Principal output |
| --- | --- | --- |
| Synthesis | XST | `blink.ngc`, `blink.syr` |
| Translate netlist and constraints | NGDBuild | `blink.ngd` |
| Map logic to device resources | MAP | `blink_map.ncd`, `blink.pcf` |
| Place and route | PAR | `blink.ncd` |
| Static timing analysis | TRACE (`trce`) | `blink.twr` |
| Generate FPGA configuration | BitGen | `blink.bit` |

`make smoke` exercises the flow using the provisional part
`xc6slx9-2-tqg144`. It provides the real 20 ns clock-period constraint but lets
ISE place the pins. After TRACE passes, BitGen runs with `-j` (the vendor's
"Don't create bit file" option), checking configuration DRC without producing
a downloadable bitstream. That mode requires a `.drc` output filename. Its
placement does not describe this carrier board.
The flow checks actual synthesis and implementation under emulation.

`make blink` uses actual board settings and runs BitGen after timing passes.
The driver checks both the zero-error/zero-score timing summary and that
`TS_clk` analyzes paths at 20 ns. It does not accept an unconstrained design's
zero-error summary as evidence of timing closure. The LED output is not a
synchronous external interface, so it does not need an external receiver
setup/hold constraint for this bring-up design.

Every stage stops on a failed command. Reports and generated project/UCF files
stay in `build/smoke/` or `build/blink/`. Each build records the image ID/digest,
part, board settings, timestamps, and source fingerprint. A successful hardware
build also records the bitstream hash; the programming command checks it and
rejects changed sources or board settings.

Allow several minutes for a smoke run under amd64 emulation. Stage logs are
flushed as output arrives; inspect `build/smoke/container.log` for progress.

## LED and board settings

The user reports the 50 MHz clock on FPGA package pin **P56**, an onboard
LED on **P143**, and 3.3 V LVCMOS I/O. Neither P56 nor P143 appears assigned in
the project spreadsheets. The user confirmed that the downloaded design blinks
the LED on P143. The template selects active-high operation.
An active-low LED will also blink at the same rate, with the on/off phases
reversed. Package pin numbers are not carrier header positions.

Use the verified onboard LED on P143. The former optional external LED pin P57
is now assigned to HP data output bit 4; P58 is assigned to HP data output bit
12. Do not attach an LED to these allocated bus pins.

The divider toggles after 25,000,000 clock cycles: 0.5 seconds on, 0.5 seconds
off at 50 MHz. Registers have explicit startup initialization. BitGen is
configured with `UnusedPin:Pullnone` so unused user I/O remains undriven.

Copy the [board template](../config/board.example.json) to
`config/board.local.json`. Fill the following fields from the carrier wiring:

| Field | Required value |
| --- | --- |
| `part` | `xc6slx9-2-tqg144`, from the reported XC6SLX9, TQG144, and `2C` markings. |
| `clock_pin` | `P56`, reported 50 MHz oscillator connection. |
| `clock_hz` | `50000000`. |
| `led_pin` | `P143`, verified by the observed blink. |
| `led_active_low` | `false` initially; change to `true` if the onboard LED is confirmed active-low. |
| `iostandard` | `LVCMOS33`, user-confirmed 3.3 V LVCMOS I/O. |

The example now contains the reported carrier settings. If
the clock and LED banks require different standards, extend the board settings
and generated UCF before using that board.

```sh
cp config/board.example.json config/board.local.json
# Edit config/board.local.json with the actual carrier information.
make blink
```

The simulation uses smaller divider values to test transitions quickly. It
does not demonstrate the real oscillator frequency, pin mapping, or LED wiring.

## JTAG download

The available adapter is a **Xilinx Platform Cable USB DLC9G clone**. The
initial programming path is native `xc3sprog` using its `xpc` backend. Its
[upstream cable documentation](https://github.com/UweBonnes/xc3sprog/blob/master/Readme.DLC10)
describes the firmware-loading step and initialized `03fd:0008` identity.

The project builds the programmer locally, with no global `xc3sprog`
installation:

```sh
brew install cmake pkgconf libftdi libusb-compat
make programmer-build
make fxload-build
make usb-scan
```

The xc3sprog source is pinned to commit
`2bba5381d64b98bca40cb83c9d1d56aaceb4c12f` with an archive checksum. The build
script adjusts its CMake dependency handling to use Homebrew's pkg-config
paths. The binary is `build/tools/xc3sprog-build/xc3sprog`. The firmware RAM
loader is built from checksum-verified examples in libusb v1.0.29 and placed
at `build/tools/fxload`. Both source provenance and build logs stay under
`build/tools/`.

On this macOS version, the useful USB report is:

```sh
system_profiler SPUSBHostDataType
```

`SPUSBDataType` returned no entries. The new `make usb-scan` command uses
`SPUSBHostDataType` and saves device names and VID/PID values without serial
numbers. It confirms the connected clone is currently **`03fd:000d`**.

The [ISE USB rules in the referenced Docker project](https://github.com/vmunoz82/ise14/blob/main/xusbdfwu.rules)
map `03fd:000d` to **`xusb_emb.hex`**, using an FX2 RAM upload. Select firmware
from the enumerated ID rather than the DLC9G label alone. The file has now
been extracted from the supplied VM archive, and all Intel HEX record
checksums were validated before uploading it.

The exact path in a full ISE image is:

```text
/opt/Xilinx/14.7/ISE_DS/ISE/bin/lin64/xusb_emb.hex
```

To extract it again from the provisioned image:

```sh
make firmware-extract
# Alternatively, use the ISE_INSTALL_DIR environment variable from provisioning.
```

This saves the file and its image identity/hash in `build/firmware/`. It reads
the file without launching ISE or requiring a license checkout. Its SHA-256 is
`c0a7a1f0110d110a2ce2a577ec1ebaf528fd066feac54f6ffc9816be22fac9d4`.

For a cold cable reporting `03fd:000d`:

```sh
make cable-firmware CABLE_FIRMWARE=build/firmware/xusb_emb.hex
make usb-scan
make jtag-detect
```

The loader targets `03fd:000d` explicitly and writes **cable RAM**, with no
EEPROM operation. Firmware may need to be reloaded after unplugging the cable.
The tested cable re-enumerated as `03fd:0008`, product name `XILINX`, after
uploading 7,458 firmware bytes. Skip the RAM upload when it is already in that
initialized state. With the target connected, `make jtag-detect` succeeded:

```text
JTAG loc.: 0  IDCODE: 0x24001093  Desc: XC6SLX9 Rev: C  IR length: 6
```

The output is saved in `build/toolchain/jtag-detect.log`. This confirms JTAG
communication with the FPGA; the reported revision does not identify its speed
grade or carrier clock pin. The driver treats an empty-chain result as a failed
detection even though xc3sprog returns zero.

Once the cable firmware is running and the powered FPGA target is connected:

```sh
make jtag-detect   # Defaults: PROGRAMMER=xc3sprog CABLE=xpc
make program
```

The second command requires a successful matching `make blink` build. It
loads volatile SRAM and leaves configuration flash untouched. Observe several
1 Hz blink cycles and record the board, cable, detected device, build identity,
and result.

openFPGALoader 1.1.1 is also installed, but its macOS build lists FTDI and
Digilent drivers and **does not list a Xilinx Platform Cable driver**. The
shared chat's `xilinxPlatformCableUsb` example is therefore not applicable to
that installed build. For a different supported adapter, select
`PROGRAMMER=openfpgaloader CABLE=<supported-name>`; see the
[openFPGALoader guide](https://trabucayre.github.io/openFPGALoader/guide/first-steps.html).

## Verified hardware milestone

On 2026-10-16, the user confirmed the LED blinks after the SRAM download.
This completes the initial build, download, and physical blink milestone.
The design produces 0.5 seconds on and 0.5 seconds off with the reported
50 MHz clock; no independent frequency measurement was made.

The hardware build receipt is `build/blink/success.json`; the bitstream is
`build/blink/blink.bit`, and the download output is
`build/toolchain/program.log`. Repeat the SRAM download with `make program`.
Power cycling removes an SRAM-only download. The separate flash-programming
milestone has now programmed and verified a persistent blink boot image.

Persistent configuration through the carrier's W25Q16JV is the next milestone;
see the [SPI flash wiring and programming guide](FLASH.md).

## HP13210 controller port

Run `make controller-sim` for 50 MHz HP bus protocol tests with the backend
disabled and with a mock backend. `make controller-smoke` implements the full
controller in ISE with a 20 ns clock constraint and runs DRC without generating
a downloadable image. See the [controller port guide](../fpga/hp13210/README.md)
for scope, reset/CDC adaptations, the retained register map, and board wiring.
The separate `make controller-build` produces a located FPGA-only carrier image;
`make controller-program` saves and verifies a fresh full-flash backup, then
programs and verifies that image and requests reload from flash. This image
disables the STM32 backend and blinks P143 at 2 Hz.
