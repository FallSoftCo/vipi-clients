#include <espeak-ng/espeak_ng.h>
#include <stdio.h>
#include <string.h>

/* Deterministic data compiler, never included in the Android application. */
int main(int argc, char **argv) {
    if (argc < 5) return 2;
    espeak_ng_InitializePath(argv[1]);
    espeak_ng_STATUS status = espeak_ng_CompileIntonationPath(argv[2], NULL, stderr, NULL);
    if (status != ENS_OK) return 3;
    status = espeak_ng_CompilePhonemeDataPath(22050, argv[2], NULL, stderr, NULL);
    if (status != ENS_OK) return 4;
    for (int index = 4; index < argc; ++index) {
        espeak_VOICE voice = {0}; voice.languages = argv[index];
        if (espeak_ng_SetVoiceByProperties(&voice) != ENS_OK) return 5;
        if (espeak_ng_CompileDictionary(argv[3], argv[index], stderr, 0, NULL) != ENS_OK) return 6;
    }
    return 0;
}
