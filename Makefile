PYTHON ?= python3
BOARD ?= config/board.local.json
CABLE ?= xpc
PROGRAMMER ?= xc3sprog
CABLE_FIRMWARE ?=

.PHONY: help doctor runtime-image runtime-check toolchain-check sim smoke blink jtag-detect program test programmer-build fxload-build cable-firmware usb-scan firmware-extract provision-ise ise-image

help:
	@echo 'make doctor          - inspect host tools, Docker, and ISE availability'
	@echo 'make runtime-image   - build the amd64 Linux runtime (no ISE included)'
	@echo 'make runtime-check   - test amd64 execution and project file sharing'
	@echo 'make toolchain-check - check installed ISE executables'
	@echo 'make provision-ise   - extract Spartan-6 CLI tools from the vendor VM ZIP'
	@echo 'make ise-image       - package the provisioned tools into a complete image'
	@echo 'make sim             - simulate the blink design with Icarus Verilog'
	@echo 'make test            - run simulation and build-validation tests'
	@echo 'make smoke           - run ISE synthesis through timing; no bitstream'
	@echo 'make blink           - build a hardware bitstream using BOARD=<json>'
	@echo 'make programmer-build - build native xc3sprog for the DLC9G cable'
	@echo 'make usb-scan         - inspect USB identities on macOS'
	@echo 'make fxload-build     - build the native cable RAM firmware loader'
	@echo 'make firmware-extract - extract xusb_emb.hex from ISE_IMAGE or ISE_INSTALL_DIR'
	@echo 'make cable-firmware CABLE_FIRMWARE=<xusb_emb.hex> - initialize 03fd:000d'
	@echo 'make jtag-detect      - detect JTAG with PROGRAMMER=xc3sprog CABLE=xpc'
	@echo 'make program          - load the matching blink bitstream into SRAM'
	@echo 'make spi-bridge       - build the carrier JTAG-to-SPI bridge and blink boot image'
	@echo 'make flash-probe      - load the bridge and read flash identity/status'
	@echo 'make flash-backup     - save and verify the original 2 MiB flash contents'
	@echo 'make flash-program    - program/verify blink in flash after a verified backup'
	@echo 'make controller-sim   - test HP13210 flags and mock-backend transactions at 50 MHz'
	@echo 'make flag-diagnostics - generate offline HP select-code 14/15 flag tests'
	@echo 'make controller-smoke - implement the full HP13210 port in ISE without a bitstream'
	@echo 'make controller-build - build the located HP controller and FSMC test SPI boot image'
	@echo 'make controller-program - back up current flash, then program/verify the controller'
	@echo 'make stm32-doctor     - inspect STM32duino, ARM compiler, CMSIS and OpenOCD'
	@echo 'make stm32-build      - build USB CDC/FSMC test firmware with CMake and Make'
	@echo 'make stm32-program    - program verified firmware with ST-Link over SWD'
	@echo 'make stm32-disk-deps  - fetch pinned STM32SD/FatFs libraries for the disk backend'
	@echo 'make stm32-disk-build - compile the separate SDIO/FAT disk backend; no download'
	@echo 'make stm32-disk-test  - run native disk-backend tests with sanitizers'
	@echo 'make stm32-disk-program - back up STM32 flash, then program/verify the disk backend'

doctor runtime-image runtime-check toolchain-check sim smoke usb-scan firmware-extract ise-image:
	$(PYTHON) scripts/fpga.py $@

blink:
	$(PYTHON) scripts/fpga.py blink --board "$(BOARD)"

jtag-detect:
	$(PYTHON) scripts/fpga.py jtag-detect --cable "$(CABLE)" --programmer "$(PROGRAMMER)"

program:
	$(PYTHON) scripts/fpga.py program --board "$(BOARD)" --cable "$(CABLE)" --programmer "$(PROGRAMMER)"

programmer-build:
	$(PYTHON) scripts/build_programmer.py

fxload-build:
	$(PYTHON) scripts/build_programmer.py --fxload

cable-firmware:
	$(PYTHON) scripts/fpga.py cable-firmware --firmware "$(CABLE_FIRMWARE)"

provision-ise:
	$(PYTHON) scripts/provision_ise.py

test: sim controller-sim controller-board-sim
	$(PYTHON) -m unittest discover -s tests -v

.PHONY: spi-bridge flash-probe flash-backup flash-program
spi-bridge:
	$(PYTHON) scripts/spi_flash.py build

flash-probe:
	$(PYTHON) scripts/spi_flash.py probe

flash-backup:
	$(PYTHON) scripts/spi_flash.py backup

flash-program:
	$(PYTHON) scripts/spi_flash.py program

.PHONY: controller-sim controller-smoke flag-diagnostics
flag-diagnostics:
	$(PYTHON) scripts/hp13210_flag_diagnostics.py

controller-sim:
	$(PYTHON) scripts/controller.py sim

controller-smoke:
	$(PYTHON) scripts/controller.py smoke

.PHONY: controller-build controller-board-sim controller-program
controller-build:
	$(PYTHON) scripts/controller_board.py build

controller-board-sim:
	$(PYTHON) scripts/controller_board.py sim

controller-program:
	$(PYTHON) scripts/controller_board.py program

.PHONY: stm32-doctor stm32-build stm32-program
stm32-doctor:
	$(PYTHON) scripts/stm32.py doctor

stm32-build:
	$(PYTHON) scripts/stm32.py build

stm32-program:
	$(PYTHON) scripts/stm32.py program

.PHONY: stm32-disk-deps stm32-disk-build stm32-disk-test stm32-disk-program
stm32-disk-deps:
	$(PYTHON) scripts/stm32_disk.py deps

stm32-disk-build:
	$(PYTHON) scripts/stm32_disk.py build

stm32-disk-test:
	$(PYTHON) scripts/stm32_disk.py test

stm32-disk-program:
	$(PYTHON) scripts/stm32_disk.py program
