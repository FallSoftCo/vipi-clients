package co.fallsoft.vipi

import org.junit.Assert.*
import org.junit.Test

class FriendInvitationLinkTest {
    @Test fun invitationAcceptsBothEntryPointsWithoutAnAuthOrMessageAction() {
        for (url in listOf("https://api.mambovipi.app/invite/Alice_123", "co.fallsoft.vipi://invite/Alice_123")) {
            assertEquals("alice_123", FriendInvitationLink.username(url))
        }
        assertEquals("friend", FriendInvitationLink.username("HTTPS://API.MAMBOVIPI.APP/invite/friend"))
    }

    @Test fun rejectsImpersonationMalformedLinksAndAuthenticationCallbacks() {
        for (url in listOf(
            "https://evil.example/invite/alice", "http://api.mambovipi.app/invite/alice",
            "https://api.mambovipi.app.evil.example/invite/alice",
            "https://alice@api.mambovipi.app/invite/bob", "https://api.mambovipi.app:443/invite/alice",
            "https://api.mambovipi.app/invite/alice?next=evil", "https://api.mambovipi.app/invite/alice#fragment",
            "https://api.mambovipi.app/invite/alice/extra", "https://api.mambovipi.app/invite/alice/",
            "https://api.mambovipi.app/invite/%61lice", "https://api.mambovipi.app/invite/%2falice",
            "https://api.mambovipi.app/invite/аlice", "https://api.mambovipi.app/invite/1alice",
            "https://api.mambovipi.app/invite/a", "https://api.mambovipi.app/invite/" + "a".repeat(25),
            "https://api.mambovipi.app/invite/admin", "https://api.mambovipi.app/invite/vBot",
            "co.fallsoft.vipi://auth/callback?code=untouched&state=untouched", "not a URL"
        )) assertNull(url, FriendInvitationLink.username(url))
    }
}
