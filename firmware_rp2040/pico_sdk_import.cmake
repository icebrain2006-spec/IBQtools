# This is a copy of <PICO_SDK_PATH>/external/pico_sdk_import.cmake

if (DEFINED ENV{PICO_SDK_PATH} AND (NOT PICO_SDK_PATH))
    set(PICO_SDK_PATH $ENV{PICO_SDK_PATH})
endif ()

# Otherwise use a reasonable default
if (NOT PICO_SDK_PATH)
    set(PICO_SDK_PATH "../../pico-sdk" CACHE PATH "Path to the Pico SDK")
endif ()

if (NOT PICO_SDK_PATH)
    message(FATAL_ERROR "SDK location was not specified. Please set PICO_SDK_PATH or PICO_SDK_FETCH_FROM_GIT.")
endif ()

get_filename_component(PICO_SDK_PATH "${PICO_SDK_PATH}" ABSOLUTE)
if (NOT EXISTS "${PICO_SDK_PATH}/pico_sdk_init.cmake")
    message(FATAL_ERROR "Directory '${PICO_SDK_PATH}' does not appear to be a Pico SDK directory")
endif ()

set(PICO_SDK_PATH "${PICO_SDK_PATH}" CACHE PATH "Path to the Pico SDK" FORCE)

include(${PICO_SDK_PATH}/pico_sdk_init.cmake)
