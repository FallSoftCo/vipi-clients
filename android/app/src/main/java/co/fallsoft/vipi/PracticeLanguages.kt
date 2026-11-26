package co.fallsoft.vipi

import android.speech.tts.TextToSpeech
import android.speech.tts.Voice
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import com.google.mlkit.nl.translate.TranslateLanguage
import kotlinx.coroutines.CompletableDeferred
import java.util.Locale

internal val translationLanguages: List<VipiLanguage> = initialLanguages + TranslateLanguage.getAllLanguages()
    .filterNot { code -> initialLanguages.any { it.code == code } }
    .map { code ->
        val locale = Locale.forLanguageTag(code)
        VipiLanguage(code, locale.getDisplayLanguage(Locale.ENGLISH), locale.getDisplayLanguage(locale))
    }.sortedBy { it.name }

internal val translationCodes = translationLanguages.mapTo(mutableSetOf()) { it.code }

internal fun translationCode(tag: String): String? {
    val locale = Locale.forLanguageTag(tag)
    return when (locale.language) {
        "cmn" -> "zh"
        "nb" -> "no"
        "fil" -> "tl"
        "iw" -> "he"
        "in" -> "id"
        else -> locale.language
    }.takeIf { it in translationCodes }
}

internal fun Voice.installedPracticeCode(): String? = if (isNetworkConnectionRequired ||
    TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED in features.orEmpty()) null else practiceVoiceLanguage(locale)

/** The system-only candidates need an actual embedded voice in the active engine. Reopening
 * the picker rechecks the device after a voice install. No voices or models are downloaded. */
@Composable internal fun systemPracticeVoices(): Set<String>? {
    val context = LocalContext.current.applicationContext
    var voices by remember(context) { mutableStateOf<Set<String>?>(null) }
    val initialized = remember(context) { CompletableDeferred<Int>() }
    val engine = remember(context) { TextToSpeech(context) { initialized.complete(it) } }
    DisposableEffect(engine) { onDispose { engine.shutdown() } }
    androidx.compose.runtime.LaunchedEffect(engine) {
        val status = kotlinx.coroutines.withTimeoutOrNull(5000) { initialized.await() }
        voices = if (status == TextToSpeech.SUCCESS) {
            try { engine.voices.orEmpty().mapNotNull { it.installedPracticeCode() }.toSet() }
            catch (_: RuntimeException) { emptySet() }
        } else emptySet()
    }
    return voices
}
