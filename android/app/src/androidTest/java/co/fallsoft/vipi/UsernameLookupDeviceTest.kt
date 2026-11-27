package co.fallsoft.vipi

import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

class UsernameLookupDeviceTest {
    @Test
    fun invitePrefixIsAcceptedOnlyAtTheBeginning() {
        assertEquals("alice_7", normalizeLookupUsername("  @Alice_7  "))
        assertEquals("alice_7", normalizeLookupUsername(" ALICE_7 "))
        for (input in listOf("@@alice", "al@ice", "@", "@ab", "@alice/name")) {
            try {
                normalizeLookupUsername(input)
                fail("Expected invalid_username for $input")
            } catch (error: ServiceFailure) {
                assertEquals("invalid_username", error.code)
            }
        }
    }
}
