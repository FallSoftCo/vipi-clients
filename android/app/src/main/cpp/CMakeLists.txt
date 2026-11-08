cmake_minimum_required(VERSION 3.22)
project(vipi_speech LANGUAGES C CXX)
set(CMAKE_C_STANDARD 99)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(VIPI_VENDOR "${CMAKE_CURRENT_LIST_DIR}/../../../../vendor")
set(ESPEAK "${VIPI_VENDOR}/espeak-ng")

# Matches the pinned eSpeak synchronous source configuration used by Apple.
# No device audio backend, async worker, MBROLA executable, or network provider.
set(ENGINE_SOURCES common mnemonics error ieee80 compiledata compiledict dictionary encoding
    intonation langopts numbers phoneme phonemelist readclause setlengths soundicon spect ssml
    synthdata synthesize tr_languages translate translateword voices wavegen speech espeak_api klatt sPlayer)
list(TRANSFORM ENGINE_SOURCES PREPEND "${ESPEAK}/src/libespeak-ng/")
list(TRANSFORM ENGINE_SOURCES APPEND ".c")
add_library(vipi_espeak STATIC ${ENGINE_SOURCES}
    "${ESPEAK}/src/ucd-tools/src/case.c" "${ESPEAK}/src/ucd-tools/src/tostring.c"
    "${ESPEAK}/src/ucd-tools/src/scripts.c" "${ESPEAK}/src/ucd-tools/src/categories.c"
    "${ESPEAK}/src/ucd-tools/src/proplist.c" "${ESPEAK}/src/ucd-tools/src/ctype.c"
    "${ESPEAK}/src/speechPlayer/src/speechPlayer.cpp"
    "${ESPEAK}/src/speechPlayer/src/frame.cpp"
    "${ESPEAK}/src/speechPlayer/src/speechWaveGenerator.cpp"
    "${VIPI_VENDOR}/sonic/sonic.c")
target_include_directories(vipi_espeak PRIVATE "${CMAKE_CURRENT_LIST_DIR}" "${ESPEAK}/src/include"
    "${ESPEAK}/src/ucd-tools/src/include" "${ESPEAK}/src/speechPlayer/include" "${VIPI_VENDOR}/sonic")
target_compile_definitions(vipi_espeak PRIVATE LIBESPEAK_NG_EXPORT=1 N_PATH_HOME=1024
    PATH_ESPEAK_DATA="/nonexistent/vipi-explicit-data-required")
target_compile_options(vipi_espeak PRIVATE -fvisibility=hidden -fwrapv)
target_link_libraries(vipi_espeak PUBLIC m)

if(ANDROID)
    add_library(vipi_speech SHARED swahili_jni.cpp)
    target_include_directories(vipi_speech PRIVATE "${ESPEAK}/src/include")
    target_link_libraries(vipi_speech PRIVATE vipi_espeak)
    target_link_options(vipi_speech PRIVATE "-Wl,-z,max-page-size=16384")
else()
    add_executable(vipi-speech-data speech_data.c)
    target_include_directories(vipi-speech-data PRIVATE "${ESPEAK}/src/include")
    target_link_libraries(vipi-speech-data PRIVATE vipi_espeak)
endif()
