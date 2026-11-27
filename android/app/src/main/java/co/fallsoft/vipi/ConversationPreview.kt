package co.fallsoft.vipi

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect

/**
 * Authored onboarding UI inputs, selected by the language the user speaks. These are not practice
 * translations; the normal local engine produces those.
 */
internal object OnboardingPreviewSource {
    private val greetings =
        mapOf(
            "en" to "Hello! How are you?",
            "es" to "¡Hola! ¿Cómo estás?",
            "fr" to "Bonjour ! Comment vas-tu ?",
            "de" to "Hallo! Wie geht es dir?",
            "it" to "Ciao! Come stai?",
            "pt" to "Olá! Como você está?",
            "ja" to "こんにちは！元気ですか？",
            "ko" to "안녕하세요! 잘 지내세요?",
            "zh" to "你好！你好吗？",
            "ar" to "مرحبًا! كيف حالك؟",
            "sw" to "Habari! Unaendeleaje?",
            "af" to "Hallo!",
            "be" to "Прывітанне!",
            "bg" to "Здравей!",
            "bn" to "নমস্কার!",
            "ca" to "Hola!",
            "cs" to "Ahoj!",
            "cy" to "Helo!",
            "da" to "Hej!",
            "el" to "Γεια σου!",
            "eo" to "Saluton!",
            "et" to "Tere!",
            "fa" to "سلام!",
            "fi" to "Hei!",
            "ga" to "Dia duit!",
            "gl" to "Ola!",
            "gu" to "નમસ્તે!",
            "he" to "שלום!",
            "hi" to "नमस्ते!",
            "hr" to "Bok!",
            "ht" to "Bonjou!",
            "hu" to "Szia!",
            "id" to "Halo!",
            "is" to "Halló!",
            "ka" to "გამარჯობა!",
            "kn" to "ನಮಸ್ಕಾರ!",
            "lt" to "Labas!",
            "lv" to "Sveiki!",
            "mk" to "Здраво!",
            "mr" to "नमस्कार!",
            "ms" to "Apa khabar?",
            "mt" to "Bongu!",
            "nl" to "Hallo!",
            "no" to "Hei!",
            "pl" to "Cześć!",
            "ro" to "Bună!",
            "ru" to "Привет!",
            "sk" to "Ahoj!",
            "sl" to "Živjo!",
            "sq" to "Përshëndetje!",
            "sv" to "Hej!",
            "ta" to "வணக்கம்!",
            "te" to "నమస్కారం!",
            "th" to "สวัสดี!",
            "tl" to "Kumusta!",
            "tr" to "Merhaba!",
            "uk" to "Привіт!",
            "ur" to "سلام!",
            "vi" to "Xin chào!",
        )
    val languages: Set<String>
        get() = greetings.keys

    fun text(source: String): String = greetings.getValue(source)

    fun translation(
        context: Context,
        source: String,
        target: String,
        translator: LanguageTranslation = LocalTranslation(),
        mode: ImmersionMode = ImmersionMode.NEW_WORD,
    ): ConversationTranslation {
        require(source in greetings)
        return ConversationTranslation(
            context,
            source,
            target,
            translator = translator,
            language =
                object : MessageTranslationLanguage {
                    override suspend fun identify(text: String): String = source

                    override fun close() = Unit
                },
            mode = mode,
        )
    }
}

/** Preview is a real local translation request, not a lookup/example catalog. */
@Composable
internal fun ConversationPreview(
    source: String,
    target: String,
    scrolling: Boolean = false,
    mode: ImmersionMode =
        if (BuildConfig.DEFAULT_FULL_IMMERSION) ImmersionMode.FULL_MESSAGES
        else ImmersionMode.NEW_WORD,
) {
    val context = LocalContext.current
    val translation =
        remember(source, target, mode) {
            OnboardingPreviewSource.translation(context, source, target, mode = mode)
        }
    val gestures = remember(source, target, mode) { FullMessageGestures().also { it.mode = mode } }
    val scope = rememberCoroutineScope()
    val speech = remember(source, target) { SpeechPlayback(context, target, scope) }
    val warmups = remember(source, target) { mapOf(source to "1", target to "1") }
    val audio =
        remember(translation, speech) { ConversationAutoplay(translation, speech, scope) {} }
    LaunchedEffect(speech) { speech.prepare(warmups) }
    LaunchedEffect(scrolling) { if (scrolling) gestures.held = false }
    LifecycleEventEffect(Lifecycle.Event.ON_STOP) { audio.background() }
    DisposableEffect(audio) { onDispose { audio.close() } }
    DisposableEffect(translation) { onDispose { translation.close() } }
    DisposableEffect(speech) { onDispose { speech.close() } }
    Column(
        Modifier.fillMaxWidth().fullMessageGestures(gestures),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        ChatBubbleFrame(false, Modifier.fillMaxWidth()) {
            FullMessageBubble(
                OnboardingPreviewSource.text(source),
                "language-preview-$source-$target",
                translation,
                gestures,
                audio,
            ) {}
        }
        FullMessageContextHint(gestures, source, target)
        SpeechPreparationHelp(speech.state, speech.error) { speech.prepare(warmups) }
    }
}

/** Actionable recovery when a selected pair cannot prepare offline speech. */
@Composable
internal fun SpeechPreparationHelp(
    state: SpeechState,
    error: String?,
    openSettings: (() -> Boolean)? = null,
    retry: () -> Unit,
) {
    val context = LocalContext.current
    var settingsError by remember { mutableStateOf(false) }
    error?.let { Text(it, fontSize = 16.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    if (state == SpeechState.UNAVAILABLE) {
        if (error == null) Text(stringResource(R.string.ui_6a8b22232bef), fontSize = 16.sp)
        if (settingsError) Text(stringResource(R.string.ui_dad92e0774f7), fontSize = 16.sp)
        Row {
            TextButton(
                onClick = {
                    settingsError =
                        !(openSettings?.invoke()
                            ?: runCatching {
                                    context.startActivity(
                                        Intent("com.android.settings.TTS_SETTINGS")
                                    )
                                }
                                .isSuccess)
                }
            ) {
                Text(stringResource(R.string.ui_8b3f05442c1b))
            }
            TextButton(
                onClick = {
                    settingsError = false
                    retry()
                }
            ) {
                Text(stringResource(R.string.ui_ed783fa140ed))
            }
        }
    }
}
