cmake_minimum_required(VERSION 3.24)
project(medwatch_rule_batch LANGUAGES CXX)

include(FetchContent)
find_package(nlohmann_json 3.11 QUIET)
if(NOT nlohmann_json_FOUND)
  set(JSON_BuildTests OFF CACHE INTERNAL "")
  FetchContent_Declare(nlohmann_json
    URL https://codeload.github.com/nlohmann/json/tar.gz/refs/tags/v3.11.3
    URL_HASH SHA256=0d8ef5af7f9794e3263480193c491549b2ba6cc74bb018906202ada498a79406
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
  FetchContent_MakeAvailable(nlohmann_json)
endif()

add_library(rule_batch_core STATIC core.cpp)
target_link_libraries(rule_batch_core PUBLIC nlohmann_json::nlohmann_json)
target_compile_features(rule_batch_core PUBLIC cxx_std_17)
set_target_properties(rule_batch_core PROPERTIES CXX_EXTENSIONS OFF POSITION_INDEPENDENT_CODE ON)

if(EMSCRIPTEN)
  target_compile_options(rule_batch_core PRIVATE -fexceptions)
  add_executable(rule_batch_wasm wasm.cpp)
  target_link_libraries(rule_batch_wasm PRIVATE rule_batch_core)
  target_compile_options(rule_batch_wasm PRIVATE -fexceptions)
  target_link_options(rule_batch_wasm PRIVATE --bind -fexceptions
    -sMODULARIZE=1 -sEXPORT_NAME=createRuleBatch -sSINGLE_FILE=1
    -sALLOW_MEMORY_GROWTH=1 -sENVIRONMENT=web,node -sDYNAMIC_EXECUTION=0)
  set_target_properties(rule_batch_wasm PROPERTIES OUTPUT_NAME engine SUFFIX ".js")
  add_custom_command(TARGET rule_batch_wasm POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory "${CMAKE_CURRENT_SOURCE_DIR}/demo" "$<TARGET_FILE_DIR:rule_batch_wasm>"
    COMMAND ${CMAKE_COMMAND} -E copy "${CMAKE_CURRENT_SOURCE_DIR}/fixtures/examples.json" "$<TARGET_FILE_DIR:rule_batch_wasm>/examples.json")
  install(TARGETS rule_batch_wasm RUNTIME DESTINATION .)
  install(DIRECTORY demo/ DESTINATION .)
  install(FILES fixtures/examples.json DESTINATION .)
else()
  add_executable(pms-rule-batch cli.cpp)
  target_link_libraries(pms-rule-batch PRIVATE rule_batch_core)
  if(MINGW)
    target_link_options(pms-rule-batch PRIVATE -municode)
  endif()
  option(PMS_PYTHON "Build the optional Python module" OFF)
  if(PMS_PYTHON)
    set(PYBIND11_FINDPYTHON ON)
    find_package(Python 3.10 COMPONENTS Interpreter Development.Module REQUIRED)
    find_package(pybind11 2.13 CONFIG REQUIRED)
    pybind11_add_module(pms_rule_batch NO_EXTRAS binding.cpp)
    target_link_libraries(pms_rule_batch PRIVATE rule_batch_core)
    install(TARGETS pms_rule_batch LIBRARY DESTINATION . RUNTIME DESTINATION .)
  endif()
endif()
