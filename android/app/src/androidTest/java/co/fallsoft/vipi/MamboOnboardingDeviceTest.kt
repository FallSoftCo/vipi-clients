package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The signed-out invite is platform-neutral and points at the public homepage. */
class MamboOnboardingDeviceTest {
    @Test fun inviteSharesOnlyTheHomepage() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val message = mamboShareMessage(context)
        assertEquals("https://mambovipi.app", VIPI_HOME_URL)
        assertTrue(message.contains(VIPI_HOME_URL))
        assertFalse(message.contains("play.google.com"))
        assertFalse(message.contains("apps.apple.com"))
        assertFalse(message.contains("Download it here"))
    }
}
