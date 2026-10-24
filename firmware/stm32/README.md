# STM32 USB/FSMC bring-up

Use **STM32duino + GNU Arm Embedded GCC + CMake-generated Makefiles**.
This keeps Arduino's USB serial and library APIs, with normal `.cpp` sources,
explicit dependencies, and direct STM32 register/HAL access. No Arduino IDE is
needed. Native STM32Cube/HAL with Make or CMake is another good option, but
Arduino libraries need adaptation there; PlatformIO is convenient but normally
builds with SCons. STM32duino's [CMake documentation](https://github.com/stm32duino/Arduino_Core_STM32/wiki/CMake-presentation)
describes this supported alternative.

## Confirmed hardware

- [DevEBox STM32F4XX-M](https://stm32-base.org/boards/STM32F407VET6-STM32F4XX-M),
  STM32F407VET6, 512 KiB flash, 8 MHz HSE crystal.
- The firmware sets 168 MHz HCLK, 42/84 MHz APB1/APB2, and 48 MHz USB clock.
- USB FS uses PA11/PA12 directly. Debug text uses USB CDC, not a USB-UART chip.
- ST-Link uses SWD on PA13/PA14 with common ground and the appropriate target
  reference connection. Keep BOOT0 low for normal flash execution.
- The user reports FSMC wire-wrapped according to the workbook. IRQ and DRQ
  remain deferred. No NE wire is required; the FPGA holds internal NE active.
- The latest FPGA image is programmed into SPI flash and cold boot is accepted.
  STM32 programming and verification passed on 2026-10-23 and the target was
  reset to run. The user confirmed the PA1 heartbeat blinks on 2026-10-23.
  Physical FSMC testing remains pending. Evidence: `build/stm32/programmed.json` and
  `build/stm32-program.log`.

## Build

```sh
make stm32-doctor
make stm32-build
# Subsequent incremental builds can also use the generated Makefile directly:
make -C build/stm32/firmware
```

The tested dependencies already installed on this Mac are STM32duino **2.9.0**,
xPack GNU Arm GCC **13.2.1-1.1**, CMSIS **5.9.0**, and CMake >=3.21. Build output
and dependency paths are recorded under `build/stm32/`; native ARM64 compilation
does not use Docker. The build generates ELF, BIN, HEX, and a linker map.

`scripts/stm32.py` detects the Arduino package paths on macOS. On another host,
install these versions using Arduino's package manager/CLI (only as a dependency
installer), or supply equivalent extracted packages and an ignored
`config/stm32.local.json`:

```json
{
  "core": "/path/to/Arduino_Core_STM32/2.9.0",
  "compiler": "/path/to/xpack-arm-none-eabi-gcc/13.2.1-1.1/bin",
  "cmsis": "/path/to/CMSIS/5.9.0",
  "openocd": "/path/to/openocd"
}
```

The helper copies the core's CMake metadata into `build/stm32/` so its generated
board database does not modify the installed package. Other installed core
sources are referenced read-only. It does not download dependencies itself.

## Scratchpad protocol

The new scratch register is a full 16-bit read/write register at **AD address
`0x000E`**. It resets to zero on FPGA board reset and survives HP POPIO. It
does not change disk status, flags, IRQ enables, or data buffers. It decodes
only the low four multiplexed address bits, as does the reference register map;
higher addresses alias and are not independent registers.

The STM32 FSMC shifts CPU byte addresses for a 16-bit memory interface. Thus
the firmware accesses **`*(volatile uint16_t *)0x6000001C`**, not `0x6000000E`.
The remaining reference AD addresses are unchanged; their CPU offsets likewise
equal twice the AD address. See ST [RM0090](https://www.st.com/resource/en/reference_manual/rm0090-stm32f407-advanced-armbased-32bit-mcus-stmicroelectronics.pdf),
FSMC NOR/PSRAM address mapping. Only aligned 16-bit accesses are supported;
byte strobes are not wired.

Pins are read from [the workbook](../../requirements/STM32F407VET.xlsx):

| Signal | STM32 pin(s), bit order low to high | FPGA pin(s), bit order low to high |
| --- | --- | --- |
| AD0–AD3 | PD14, PD15, PD0, PD1 | P100, P99, P98, P97 |
| AD4–AD12 | PE7–PE15 | P95, P94, P93, P92, P88, P87, P85, P84, P83 |
| AD13–AD15 | PD8, PD9, PD10 | P82, P81, P80 |
| NOE | PD4 | P79 |
| NWE | PD5 | P78 |
| NADV / FSMC_NL | PB7 | P75 |

The initial configuration uses AF12 and asynchronous multiplexed PSRAM mode A,
16-bit width, no WAIT or burst, and BTR fields ADDSET=15, ADDHLD=15, DATAST=63,
BUSTURN=15. Address setup/hold and turnaround are approximately 90–96 ns;
the data phase is approximately 375–381 ns at 168 MHz, depending on phase rules.
These are conservative starting settings for the FPGA's 50 MHz synchronizers,
not a measured limit. Confirm actual waveforms and bus turnaround on hardware.
STM32 pull-ups and FPGA weak pull-ups keep control strobes idle high when not
actively driven; the boards must be powered appropriately for the test.

## Run later, when the programmers are connected

The firmware pulses the onboard active-low **PA1 LED for 100 ms every two
seconds** while the FSMC test is stopped. It starts automatically after reset,
including without a USB terminal or DTR. No FSMC accesses occur until `t` is
received. Starting the test changes the LED to the latest pass/fail indication;
`s` stops the test and restores the heartbeat.

1. Build the matching FPGA image with `make controller-build`; program it
   separately with `make controller-program` when the FPGA JTAG is connected.
   The latest FPGA image was programmed into SPI flash and verified on
   2026-10-23; physical FSMC read/write testing is still pending.
2. Connect ST-Link and program with `make stm32-program`. This explicit target
   uses OpenOCD `interface/stlink.cfg` and `target/stm32f4x.cfg` and verifies the
   ELF before reset. Build targets never program either device.
3. Open the STM32 USB CDC serial port in a terminal and assert DTR (normal
   serial-terminal behavior). Send **`t`** to start repeated tests; **`s`** stops.
4. Each pass writes 294 patterns: six fixed values, walking ones and zeros,
   and 256 LFSR values. Each write is followed by two reads. The terminal shows
   expected/actual values on failure and a running pass/failure count. PA1's
   active-low LED lights for a passing test and turns off for a failed test.

An initial PASS proves this register's read/write data path at these settings;
it does not prove all address lines, the disk protocol, or worst-case timing.
Do not run disk/backend firmware concurrently with this transport test.

## SD-card libraries later

[SdFat](https://github.com/greiman/SdFat) can be linked as a CMake dependency
with STM32duino, particularly for an SPI-connected card. The optional
`SDFAT_PATH` CMake setting accepts a checkout in a directory named `SdFat`;
third-party library generation needs Python `jinja2`. This optional integration
has not been built or tested in this milestone.

This carrier's on-board socket is wired for **SDIO** (PC8–PC12 and PD2), rather
than the usual SPI wiring. For that socket, prefer the STM32duino
[STM32SD library](https://github.com/stm32duino/STM32SD), which uses FatFs and
supports SDIO, or plan a specific SdFat transport adaptation. Retaining Arduino
APIs does not automatically provide SdFat SDIO support on the F407. Disk image
storage and filesystem selection remain separate from this FSMC test.
