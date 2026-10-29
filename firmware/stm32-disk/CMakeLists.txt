cmake_minimum_required(VERSION 3.21)
set(CMAKE_TOOLCHAIN_FILE "${CMAKE_CURRENT_LIST_DIR}/../stm32/cmake/arm-toolchain.cmake")
project(hp13210_disk LANGUAGES C CXX ASM)
list(APPEND CMAKE_MODULE_PATH "${CORE_PATH}/cmake")
include(set_board)
set_board(GENERIC_F407VETX SERIAL disabled USB CDCgen XUSB FS)
include(overall_settings)
overall_settings(DEBUG_SYMBOLS OPTIMIZATION s)
include(build_sketch)
build_sketch(TARGET disk_backend SOURCES src/main.cpp src/platform.cpp src/backend.cpp src/config.cpp DEPENDS USBDevice)
# Polling SDIO shares the CPU with USB/SysTick. At 24 MHz the real carrier
# recorded TX FIFO underrun after thousands of diagnostic writes. Give the
# polling loop six times the service margin: 48 MHz / (10 + 2) = 4 MHz.
target_compile_definitions(base_config INTERFACE HSE_VALUE=8000000U SD_DATATIMEOUT=1000U SD_CLK_DIV=10U)

foreach(lib STM32SD FatFs)
  if(NOT EXISTS "${DISK_DEPS}/${lib}/library.properties")
    message(FATAL_ERROR "Missing ${lib}; run make stm32-disk-deps")
  endif()
  target_include_directories(base_config INTERFACE "${DISK_DEPS}/${lib}/src")
  file(GLOB_RECURSE lib_sources CONFIGURE_DEPENDS "${DISK_DEPS}/${lib}/src/*.c" "${DISK_DEPS}/${lib}/src/*.cpp")
  target_sources(disk_backend PRIVATE ${lib_sources})
endforeach()
