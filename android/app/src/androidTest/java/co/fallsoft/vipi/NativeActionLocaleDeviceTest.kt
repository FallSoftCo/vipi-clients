package co.fallsoft.vipi

import android.content.res.Configuration
import android.view.accessibility.AccessibilityNodeInfo
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionResult
import co.fallsoft.vipi.core.ImmersionSpan
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.util.Locale

class NativeActionLocaleDeviceTest {
    @get:Rule val compose = createComposeRule()

    @Test fun spanishNativeActionsRetainUniquePositionsAndOverflow() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val base = instrumentation.targetContext
        val configuration = Configuration(base.resources.configuration).apply { setLocale(Locale.forLanguageTag("es")) }
        val localized = base.createConfigurationContext(configuration)
        val source = List(33) { "music" }.joinToString(" ")
        val target = List(33) { "muziki" }.joinToString(" ")
        val result = ImmersionResult(source, target, (0..32).map { index ->
            ImmersionSpan(index * 6, index * 6 + 5, "music", "muziki", index * 7, index * 7 + 6)
        })
        compose.setContent {
            CompositionLocalProvider(LocalContext provides localized) {
                VipiTheme(Appearance.LIGHT) {
                    ImmersionBubble(result, ReadingMode.IMMERSED, source = "en", target = "sw", embedded = true, contextualActions = true)
                }
            }
        }
        fun nodes(root: AccessibilityNodeInfo): List<AccessibilityNodeInfo> = listOf(root) +
            (0 until root.childCount).flatMap { root.getChild(it)?.let(::nodes) ?: emptyList() }
        val automation = instrumentation.uiAutomation
        lateinit var node: AccessibilityNodeInfo
        compose.waitUntil(10_000) {
            val root = automation.rootInActiveWindow
            val found = root?.let(::nodes).orEmpty().firstOrNull { item -> item.actionList.any { it.label?.toString() == "Elige una palabra para cambiar" } }
            if (found != null) node = found
            found != null
        }
        val labels = node.actionList.mapNotNull { it.label?.toString() }
        val wordLabels = labels.filter { it.startsWith("Cambiar music y muziki, palabra ") }
        assertEquals(30, wordLabels.size)
        assertEquals(30, wordLabels.toSet().size)
        assertTrue("Cambiar music y muziki, palabra 1" in wordLabels)
        assertTrue("Cambiar music y muziki, palabra 30" in wordLabels)
        assertTrue("Acciones del mensaje" in labels)
        val choose = node.actionList.first { it.label?.toString() == "Elige una palabra para cambiar" }
        assertTrue(node.performAction(choose.id))
        compose.waitUntil(5_000) { automation.rootInActiveWindow?.let(::nodes).orEmpty().any { it.text?.toString() == "Cambiar una palabra" } }
        assertNotNull(automation.rootInActiveWindow)
    }
}
