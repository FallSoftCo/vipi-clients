package co.fallsoft.vipi

import android.content.Context
import android.icu.util.ULocale
import android.speech.tts.TextToSpeech
import android.speech.tts.Voice
import androidx.compose.runtime.Composable
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import com.google.mlkit.nl.translate.TranslateLanguage
import java.util.Locale
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeoutOrNull

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

/** Earlier releases could persist just one side when the other still matched the device default. */
internal fun restoredLanguagePair(known: String?, target: String?, deviceTag: String): Pair<String, String> {
    val savedSource = known?.let(::translationCode)
    val savedTarget = target?.let(::translationCode)
    val device = translationCode(deviceTag) ?: "en"
    val source = savedSource ?: device.takeUnless { it == savedTarget } ?: if (savedTarget == "en") "es" else "en"
    val practice = savedTarget?.takeUnless { it == source } ?: if (source == "en") "es" else "en"
    return source to practice
}

internal fun Voice.installedPracticeCode(): String? = if (isNetworkConnectionRequired ||
    TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED in features.orEmpty()) null else practiceVoiceLanguage(locale)

/** Recheck the active engine when a picker opens or returns from speech settings. */
internal suspend fun installedPracticeVoices(context: Context): Set<String> {
    val initialized = CompletableDeferred<Int>()
    val engine = TextToSpeech(context.applicationContext) { initialized.complete(it) }
    return try {
        if (withTimeoutOrNull(5000) { initialized.await() } == TextToSpeech.SUCCESS)
            engine.voices.orEmpty().mapNotNull { it.installedPracticeCode() }.toSet()
        else emptySet()
    } catch (cancelled: CancellationException) { throw cancelled }
    catch (_: RuntimeException) { emptySet() }
    finally { engine.shutdown() }
}

internal class PracticeOptions(private val bundled: Set<String>, private val installed: Set<String>?) {
    fun missingVoice(code: String) = installed != null && code !in bundled && code !in installed

    fun targets(source: String?, saved: String?) = translationLanguages.filter { language ->
        val code = language.code
        code != source && (code == saved || (code in readableCodes && (code in bundled || code in installed.orEmpty())))
    }

    private companion object {
        val readableCodes = translationCodes.filterTo(mutableSetOf()) {
            FullMessageReadings.supports(it) || ULocale.addLikelySubtags(ULocale.forLanguageTag(it)).script == "Latn"
        }
    }
}

@Composable internal fun rememberPracticeOptions(): PracticeOptions {
    val context = LocalContext.current.applicationContext
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val bundled = remember(context) { BundledVoiceData.voices(context).keys }
    val installed = produceState<Set<String>?>(null, context, lifecycle) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) { value = installedPracticeVoices(context) }
    }.value
    return remember(bundled, installed) { PracticeOptions(bundled, installed) }
}
