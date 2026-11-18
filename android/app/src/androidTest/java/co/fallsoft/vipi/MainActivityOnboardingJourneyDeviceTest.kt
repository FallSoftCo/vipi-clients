package co.fallsoft.vipi

import android.content.ActivityNotFoundException
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.Locale
import java.util.concurrent.atomic.AtomicInteger

/** Real MainActivity navigation + real native preview. Auth launch is an explicit
 * local boundary: no browser, credentials, token exchange or backend call. */
class MainActivityOnboardingJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test fun firstLaunchLanguagePreviewConsentAuthErrorBackAndRecreationKeepContext() {
        MainActivityJourneyFixture("onboarding").use { f ->
            val launches = AtomicInteger()
            var blockLaunch = true
            f.instrumentation.runOnMainSync {
                f.model.authentication.qualificationSignInLaunch = { uri ->
                    launches.incrementAndGet()
                    check(uri.getQueryParameter("redirect_uri") == "co.fallsoft.vipi://auth/callback")
                    check(!uri.getQueryParameter("code_challenge").isNullOrBlank())
                    if (blockLaunch) throw ActivityNotFoundException("Synthetic browser unavailable")
                }
            }
            fun text(id: Int) = f.base.getString(id)
            val largeText = f.base.resources.configuration.fontScale >= 1.5f
            fun waitScreen(screen: Screen) = compose.waitUntil(8_000) { f.model.screen == screen }
            fun action(id: Int): SemanticsNodeInteraction = compose.onNodeWithText(text(id)).also {
                // Production moves these actions into the page at large type.
                if (largeText) it.performScrollTo()
            }
            fun revealParagraph(original: String) {
                fun visible(): Boolean {
                    var shown = false
                    f.instrumentation.runOnMainSync { shown = f.paragraphs().any { it.displayedOriginal == original && f.fullyVisible(it) } }
                    return shown
                }
                // Native paragraph contents change as the preview flips. Use
                // actual page swipes rather than matching a transient projection.
                repeat(6) {
                    if (!visible()) compose.onNode(hasScrollAction()).performTouchInput {
                        swipeUp(startY = height * .8f, endY = height * .55f)
                    }
                }
                compose.waitUntil(5_000) { visible() }
            }
            fun language(code: String) = Locale.forLanguageTag(code).getDisplayLanguage(f.base.resources.configuration.locales[0])
                .replaceFirstChar { it.titlecase(f.base.resources.configuration.locales[0]) }
            try {
                f.launch()
                waitScreen(Screen.WELCOME)
                compose.onNodeWithText(text(R.string.welcome_title_concise)).assertIsDisplayed()
                compose.onNodeWithText(text(R.string.welcome_detail_concise)).assertIsDisplayed()
                // Preserve the no-scroll requirement at normal type. Large
                // system type deliberately uses the accessible scrolling page.
                if (!largeText) compose.onNodeWithText(text(R.string.choose_languages)).assertIsDisplayed()
                revealParagraph(immersionPreview.original)
                compose.waitUntil(5_000) {
                    var shown = false
                    f.instrumentation.runOnMainSync { shown = f.paragraphs().any { it.displayedOriginal == immersionPreview.original && f.fullyVisible(it) } }
                    shown
                }
                f.capture("01-welcome-example-and-forward-action")
                action(R.string.choose_languages).assertIsDisplayed().performTouchInput { click() }
                waitScreen(Screen.LANGUAGE)
                compose.onNodeWithContentDescription(text(R.string.ui_aae89a15c1be)).performScrollTo().performTouchInput { click() }
                compose.onNodeWithText(language("fr")).performScrollTo().performTouchInput { click() }
                compose.onNodeWithContentDescription(text(R.string.ui_0c574552109f)).performScrollTo().performTouchInput { click() }
                compose.onNodeWithText("${language("zh")} · 中文").performScrollTo().performTouchInput { click() }
                compose.runOnIdle { assertEquals("fr", f.model.knownLanguage); assertEquals("zh", f.model.targetLanguage) }
                // Scroll the actual production page to reveal the changed example.
                val expected = ConversationExamples.result(f.base, "fr", "zh")
                revealParagraph(expected.original)
                compose.waitUntil(8_000) {
                    var ready = false
                    f.instrumentation.runOnMainSync {
                        ready = f.paragraphs().any { view ->
                            view.displayedOriginal == expected.original && f.fullyVisible(view) &&
                                view.visibleText().any { it in "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ" }
                        }
                    }
                    ready
                }
                f.capture("02-selected-languages-with-marked-chinese-preview")
                if (largeText) {
                    // A tall example is read by scrolling. Deliberately expose
                    // its lower portion and the existing forward action too.
                    compose.onNode(hasScrollAction()).performTouchInput { swipeUp() }
                    action(R.string.continue_action).assertIsDisplayed()
                    f.capture("02b-large-preview-bottom-and-forward-action-after-scroll")
                }
                action(R.string.continue_action).performTouchInput { click() }
                waitScreen(Screen.ACCOUNT)
                compose.onNodeWithText(text(R.string.account_trial_concise)).performScrollTo().assertIsDisplayed()
                action(R.string.continue_signin).assertIsNotEnabled()
                val consent = compose.onNode(hasText(text(R.string.ui_9ed65d7add5f)) and SemanticsMatcher.expectValue(androidx.compose.ui.semantics.SemanticsProperties.Role, Role.Checkbox))
                if (largeText) consent.performScrollTo()
                consent.assertIsOff().performTouchInput { click(center + androidx.compose.ui.geometry.Offset(center.x - 12f, 0f)) }
                consent.assertIsOn()
                action(R.string.continue_signin).assertIsEnabled().performTouchInput { click() }
                compose.onNodeWithText(text(R.string.ui_79290727c58b)).assertIsDisplayed()
                compose.runOnIdle { assertEquals(1, launches.get()); assertNull(f.model.authentication.userID) }
                f.capture("03-auth-open-error-retains-language-and-retry")
                f.device.pressBack()
                waitScreen(Screen.LANGUAGE)
                compose.onNodeWithText(language("fr")).performScrollTo().assertIsDisplayed()
                compose.onNodeWithText(language("zh")).performScrollTo().assertIsDisplayed()
                f.recreate()
                waitScreen(Screen.LANGUAGE)
                compose.runOnIdle { assertEquals("fr", f.model.knownLanguage); assertEquals("zh", f.model.targetLanguage) }
                action(R.string.continue_action).performTouchInput { click() }
                waitScreen(Screen.ACCOUNT)
                // A recreated native page still requires the explicit forward action;
                // neither Back nor recreation opens a second auth attempt.
                compose.runOnIdle { assertEquals(1, launches.get()); blockLaunch = false }
                val accepted = compose.onNode(hasText(text(R.string.ui_9ed65d7add5f)) and SemanticsMatcher.expectValue(androidx.compose.ui.semantics.SemanticsProperties.Role, Role.Checkbox))
                if (largeText) accepted.performScrollTo()
                if (accepted.fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.ToggleableState] != androidx.compose.ui.state.ToggleableState.On) {
                    accepted.performTouchInput { click() }
                }
                action(R.string.continue_signin).performTouchInput { click() }
                compose.runOnIdle { assertEquals(2, launches.get()); assertNull(f.model.authentication.error) }
                f.capture("04-auth-launch-boundary-context-preserved")
                File(f.output, "result.json").writeText(JSONObject().put("pass", true)
                    .put("actual_activity", "MainActivity").put("native_preview_tone_marks", true)
                    .put("auth_launches", 2).put("known", "fr").put("learning", "zh")
                    .put("large_preview_bottom_and_forward_action_reviewed_by_scroll", largeText)
                    .put("entire_tall_preview_simultaneously_visible_claimed", false)
                    .put("external_browser_or_exchange", false).put("human_comprehension_claimed", false).toString(2))
            } catch (failure: Throwable) {
                runCatching { f.capture("failure-before-cleanup") }.onFailure { failure.addSuppressed(it) }
                throw failure
            }
        }
    }
}
