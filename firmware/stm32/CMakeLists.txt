cmake_minimum_required(VERSION 3.21)
set(CMAKE_TOOLCHAIN_FILE "${CMAKE_CURRENT_LIST_DIR}/cmake/arm-toolchain.cmake")
project(hp21xx_stm32 LANGUAGES C CXX ASM)

list(APPEND CMAKE_MODULE_PATH "${CORE_PATH}/cmake")
include(set_board)
set_board(GENERIC_F407VETX SERIAL disabled USB CDCgen XUSB FS)
include(overall_settings)
overall_settings(DEBUG_SYMBOLS OPTIMIZATION s)
include(build_sketch)
build_sketch(TARGET fsmc_test SOURCES src/main.cpp DEPENDS USBDevice)
target_compile_definitions(base_config INTERFACE HSE_VALUE=8000000U)

# Optional later integration: SdFat's SPI transport needs no Arduino IDE.
# An SDIO transport for this carrier's on-board socket is a separate task.
if(DEFINED SDFAT_PATH)
  include(external_library)
  external_library(PATH "${SDFAT_PATH}")
  target_link_libraries(fsmc_test PRIVATE SdFat)
endif()
