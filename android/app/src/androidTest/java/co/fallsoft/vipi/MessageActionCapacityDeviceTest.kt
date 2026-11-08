package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionResult
import co.fallsoft.vipi.core.ImmersionSpan
import org.junit.Assert.*
import org.junit.Test

class MessageActionCapacityDeviceTest {
    @Test fun nativeMessageActionAndOverflowWordChooserHaveSeparateSlots() {
        val ins = InstrumentationRegistry.getInstrumentation()
        // Accessibility capacity fixture only, not translation/coverage evidence.
        val source = List(33) { "music" }.joinToString(" ")
        val target = List(33) { "muziki" }.joinToString(" ")
        val result = ImmersionResult(source, target, (0..32).map { index ->
            ImmersionSpan(index * 6, index * 6 + 5, "music", "muziki", index * 7, index * 7 + 6)
        })
        ins.runOnMainSync {
            var messageCalls = 0; var chooserCalls = 0; var switched = -1
            val view = StableImmersionText(ins.targetContext)
            view.onWord = { switched = it }; view.onChooseWord = { chooserCalls++ }
            view.bind(result, emptySet(), false, 0xff000000.toInt(), 0xff000000.toInt())
            view.configureMessageActions({ messageCalls++ }, false) {}
            val node = view.createAccessibilityNodeInfo()
            val switches = node.actionList.filter { it.label?.toString()?.startsWith("Switch music and muziki") == true }
            assertEquals(30, switches.size)
            assertTrue(view.performAccessibilityAction(switches.last().id, null)); assertEquals(result.spans[29].id, switched)
            val chooser = node.actionList.single { it.label?.toString() == "Choose a word to switch" }
            assertTrue(view.performAccessibilityAction(chooser.id, null)); assertEquals(1, chooserCalls)
            val named = node.actionList.filter { it.label?.toString() == "Message actions" }
            assertEquals("One named action, distinct from native long-click: ${node.actionList}", 1, named.size)
            assertNotEquals(android.view.accessibility.AccessibilityNodeInfo.ACTION_LONG_CLICK, named.single().id)
            // This detached fixture covers custom action allocation/callbacks;
            // native long-click advertisement belongs to the attached UI test.
            val message = named.single()
            assertTrue(view.performAccessibilityAction(message.id, null)); assertEquals(1, messageCalls)
        }
    }
}
