package co.fallsoft.vipi

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class OnboardingVoiceHelpDeviceTest {
 @get:Rule val compose = createComposeRule()
 @Test fun unavailableVoiceOffersAccessibleRecovery() {
  check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true")
  var retries=0;var settings=0
  val state=mutableStateOf(SpeechState.UNAVAILABLE)
  compose.setContent {
   CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density,2f)) {
    VipiTheme(Appearance.DARK) {
     Column(Modifier.verticalScroll(rememberScrollState())) {
      SpeechPreparationHelp(state.value,"Download a Japanese voice in your phone’s speech settings, then retry.",openSettings={settings++;false}) { retries++;state.value=SpeechState.PREPARING }
     }
    }
   }
  }
  compose.onNodeWithText("Speech settings").assertHasClickAction().performScrollTo().performClick()
  compose.onNodeWithText("Open your phone’s Settings and search for text-to-speech.").performScrollTo().assertIsDisplayed()
  compose.onNodeWithText("Retry voices").assertHasClickAction().performScrollTo().performClick()
  compose.runOnIdle { assertEquals(1,settings);assertEquals(1,retries) }
  compose.onNodeWithText("Retry voices").assertDoesNotExist()
 }
 @Test fun notificationDenialOffersSettingsAtLargeText() {
  check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true")
  var clicks=0;val asked=mutableStateOf(false);val unavailable=mutableStateOf(false)
  compose.setContent {
   CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density,2f)) {
    VipiTheme(Appearance.DARK) {
     Column(Modifier.verticalScroll(rememberScrollState())) {
      NotificationPrompt(asked.value,unavailable.value) { clicks++; if (!asked.value) asked.value=true else unavailable.value=true }
     }
    }
   }
  }
  compose.onNodeWithText("Enable notifications").assertHasClickAction().performClick()
  compose.onNodeWithText("Notification settings").assertHasClickAction().performClick()
  compose.onNodeWithText("Open Vipi’s notification settings in Android Settings.").performScrollTo().assertIsDisplayed()
  compose.runOnIdle { assertEquals(2,clicks) }
 }
}
