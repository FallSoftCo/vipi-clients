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

# Pinned Apache-2.0 CLD2 source and static tables; no model download.
if(ANDROID)
    set(CLD2_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../../../vendor/cld2")
    set(CLD2_SOURCES cld2_generated_cjk_compatible cld2_generated_deltaocta0122 cld2_generated_distinctocta0122 cld2_generated_quad0122 cld_generated_cjk_delta_bi_32 cld_generated_cjk_uni_prop_80 cld_generated_score_quad_octa_0122 cldutil cldutil_shared compact_lang_det compact_lang_det_hint_code compact_lang_det_impl debug fixunicodevalue generated_distinct_bi_0 generated_entities generated_language generated_ulscript getonescriptspan lang_script offsetmap scoreonescriptspan tote utf8statetable)
    list(TRANSFORM CLD2_SOURCES PREPEND "${CLD2_ROOT}/internal/")
    list(TRANSFORM CLD2_SOURCES APPEND ".cc")
    add_library(vipi_language SHARED language_jni.cpp ${CLD2_SOURCES})
    target_include_directories(vipi_language PRIVATE "${CLD2_ROOT}/public" "${CLD2_ROOT}/internal")
    target_compile_options(vipi_language PRIVATE -Wno-narrowing -fvisibility=hidden)
    target_link_options(vipi_language PRIVATE "-Wl,-z,max-page-size=16384")
endif()
