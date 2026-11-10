#pragma once
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
// Returns an immutable process-lifetime language code, or NULL. Never retains input.
const char *vipi_detect_language(const char *utf8, size_t length);
#ifdef __cplusplus
}
#endif
