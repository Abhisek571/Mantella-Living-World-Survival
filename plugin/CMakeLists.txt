cmake_minimum_required(VERSION 3.21)

project(MLWS_Listener VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# Static C++ runtime: the DLL does not depend on the Visual C++ Redistributable installed on the
# player's PC (an outdated one crashes plugins built with a newer compiler while they load).
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

# Keep build-machine paths out of the binary (__FILE__ / source_location).
file(TO_NATIVE_PATH "${CMAKE_SOURCE_DIR}/" MLWS_SOURCE_ROOT)
add_compile_options("/d1trimfile:${MLWS_SOURCE_ROOT}")

set(ENABLE_SKYRIM_SE ON CACHE BOOL "" FORCE)
set(ENABLE_SKYRIM_AE ON CACHE BOOL "" FORCE)
set(ENABLE_SKYRIM_VR ON CACHE BOOL "" FORCE)
set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory(lib/commonlibsse-ng CommonLibSSE EXCLUDE_FROM_ALL)
get_target_property(COMMONLIB_SRC_DIR CommonLibSSE SOURCE_DIR)
include(${COMMONLIB_SRC_DIR}/cmake/CommonLibSSE.cmake)

add_commonlibsse_plugin(${PROJECT_NAME}
	AUTHOR "itsPigeon2000"
	SOURCES
		src/main.cpp
		src/Survival.cpp
)
target_compile_definitions(${PROJECT_NAME} PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX UNICODE _UNICODE)
target_compile_options(${PROJECT_NAME} PRIVATE /Zc:preprocessor /utf-8)
target_precompile_headers(${PROJECT_NAME} PRIVATE src/PCH.h)
target_include_directories(${PROJECT_NAME} PRIVATE src)
