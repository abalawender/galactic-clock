cmake_minimum_required(VERSION 3.12)

set(NAME galactic-clock)

include(pico_sdk_import.cmake)
include(pimoroni_pico_import.cmake)

# Gooey boilerplate
project(${NAME} C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# Initialize the SDK
pico_sdk_init()

add_executable(${NAME}
    main.cpp
    ntp.c
)

target_include_directories(${NAME} PRIVATE ${CMAKE_CURRENT_LIST_DIR} )

# This assumes `pimoroni-pico` is stored alongside the project
include(libraries/galactic_unicorn/galactic_unicorn)
include(libraries/pico_wireless/pico_wireless)

target_link_libraries(${NAME}
    pico_stdlib
    hardware_pio
    hardware_adc
    hardware_dma
    pico_graphics
    galactic_unicorn
    pico_cyw43_arch_lwip_threadsafe_background
)

pico_enable_stdio_usb(${NAME} 1)
pico_enable_stdio_uart(${NAME} 0)

# create map/bin/hex file etc.
pico_add_extra_outputs(${NAME})

# Set up files for the release packages
install(FILES
    ${CMAKE_CURRENT_BINARY_DIR}/${NAME}.uf2
    ${CMAKE_CURRENT_LIST_DIR}/README.md
    DESTINATION .
)

set(CPACK_INCLUDE_TOPLEVEL_DIRECTORY OFF)
set(CPACK_GENERATOR "ZIP" "TGZ")
include(CPack)