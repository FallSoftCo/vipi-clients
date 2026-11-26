package co.fallsoft.vipi

import android.content.res.Configuration
import android.net.Uri
import android.os.LocaleList
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import org.junit.Rule
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Native guest onboarding and incoming links share the same consent-gated sign-in. */
class MamboOnboardingDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test fun guestCanOpenSignInAndResumeAnIncomingInvitation() {
        MainActivityJourneyFixture("mambo-invite").use { f ->
            f.launch()
            compose.onNodeWithTag("mambo-sign-in").performClick()
            val signIn = compose.onNodeWithTag("mambo-create-account")
            signIn.assertIsNotEnabled()
            compose.onNodeWithTag("mambo-not-now").performClick()
            compose.onNodeWithTag("mambo-name-title").assertIsDisplayed()
        }
        MainActivityJourneyFixture("mambo-guest-invitation").use { f ->
            f.launch(Uri.parse("https://api.mambovipi.app/invite/qa_friend"))
            val heading = f.base.getString(R.string.inbox_invited_account, "qa_friend")
            compose.onNodeWithText(heading).assertIsDisplayed()
            f.capture("01-invitation")
            compose.onNodeWithTag("inbox-sign-in").performClick()
            val signIn = compose.onNodeWithTag("mambo-create-account")
            signIn.assertIsNotEnabled()
            compose.onNodeWithTag("mambo-terms").performClick()
            signIn.assertIsEnabled().assertTextContains(f.base.getString(R.string.inbox_sign_in))
            f.capture("02-sign-in-consent")
            compose.onNodeWithTag("mambo-not-now").performClick()
            f.recreate()
            compose.onNodeWithText(heading).assertIsDisplayed()
            f.relaunch { VipiModel(it, NoJourneyModelTranslation) }
            compose.onNodeWithText(heading).assertIsDisplayed()
            assertEquals("qa_friend", f.model.invitationUsername)
            assertEquals(null, f.model.authentication.userID)
        }
    }

    @Test fun inviteSharesOnlyTheHomepage() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        for (locale in listOf("ar", "de", "es", "fr", "it", "ja", "ko", "pt-PT", "pt-BR", "sw", "zh-CN", "zh-TW")) {
            val configuration = Configuration(context.resources.configuration).apply { setLocales(LocaleList.forLanguageTags(locale)) }
            val localized = context.createConfigurationContext(configuration)
            for (key in listOf(R.string.mambo_meaning, R.string.mambo_account_detail, R.string.inbox_invited_account)) {
                assertFalse(locale, context.createConfigurationContext(Configuration(configuration).apply {
                    setLocales(LocaleList.forLanguageTags("en"))
                }).getString(key, "qa_friend") == localized.getString(key, "qa_friend"))
            }
            assertTrue(mamboShareMessage(localized).endsWith("\n$VIPI_HOME_URL"))
            assertTrue(localized.getString(R.string.inbox_invited_account, "qa_friend").contains("@qa_friend"))
        }
        val message = mamboShareMessage(context)
        assertEquals("https://mambovipi.app", VIPI_HOME_URL)
        assertTrue(message.contains(VIPI_HOME_URL))
        assertFalse(message.contains("play.google.com"))
        assertFalse(message.contains("apps.apple.com"))
        assertFalse(message.contains("Download it here"))
    }
}
