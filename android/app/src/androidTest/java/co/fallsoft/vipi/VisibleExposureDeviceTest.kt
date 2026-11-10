package co.fallsoft.vipi

import android.content.Intent
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SourceReferencePresentation
import co.fallsoft.vipi.core.SourceReferenceUnit
import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.atomic.AtomicInteger

class VisibleExposureDeviceTest {
    @Test fun clippedBubbleDoesNotEarnExposure() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val exposure = AtomicInteger(0)
        val height = mutableStateOf(24)
        val result = requireNotNull(SourceReferencePresentation.create("We shared ice cream after dinner at home.","sw",
            listOf(SourceReferenceUnit(10,19,"ice cream","aiskrimu",null,"qa-ice-cream","a".repeat(64),nativeSourceTokens=2)),.75,8))
        val scenario = ActivityScenario.launch<MainActivity>(Intent(context,MainActivity::class.java).putExtra("vipi_screen","welcome"))
        try {
            scenario.onActivity { activity -> activity.setContent {
                VipiTheme(Appearance.LIGHT) {
                    Box(Modifier.height(height.value.dp).clipToBounds()) {
                        Box(Modifier.wrapContentHeight(unbounded=true)) {
                            ImmersionBubble(result,ReadingMode.IMMERSED,targetDwellMs=600,meaningDwellMs=300,
                                onExposure={ exposure.addAndGet(it.size) })
                        }
                    }
                }
            } }
            android.os.SystemClock.sleep(2400)
            assertEquals("A clipped bubble cannot credit unseen words",0,exposure.get())
            instrumentation.runOnMainSync { height.value=400 }
            android.os.SystemClock.sleep(2400)
            assertTrue("The same fully visible bubble earns exposure",exposure.get()>0)
        } finally { scenario.close() }
    }
}
