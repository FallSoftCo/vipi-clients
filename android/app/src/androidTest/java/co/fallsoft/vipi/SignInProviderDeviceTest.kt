package co.fallsoft.vipi

import android.net.Uri
import org.junit.Assert.*
import org.junit.Test

class SignInProviderDeviceTest {
    private val start = "https://api.workos.com/user_management/authorize?client_id=client_fixture&redirect_uri=co.fallsoft.vipi%3A%2F%2Fauth%2Fcallback&response_type=code&state=state%2Bfixture&code_challenge=challenge_fixture&code_challenge_method=S256&provider=old&provider=other&max_age=90&screen_hint=sign-up"

    @Test fun providerSelectionPreservesOriginalPKCEStateAndExactCallback() {
        for (provider in SignInProvider.entries) {
            val url = signInAuthorizationURL(start, provider, reauthenticate = false)
            val original = Uri.parse(start)
            assertEquals(listOf(provider.workosProvider), url.getQueryParameters("provider"))
            for (name in listOf("client_id", "redirect_uri", "response_type", "state", "code_challenge", "code_challenge_method")) {
                assertEquals(original.getQueryParameters(name), url.getQueryParameters(name))
            }
            assertNull(url.getQueryParameter("max_age"))
            assertNull(url.getQueryParameter("screen_hint"))
            assertNull(url.getQueryParameter("client_secret"))
            assertEquals(original.scheme, url.scheme)
            assertEquals(original.authority, url.authority)
            assertEquals(original.path, url.path)
        }
    }

    @Test fun sameAccountReauthenticationAlwaysUsesAuthKitFreshFactorSelection() {
        for (provider in SignInProvider.entries) {
            val url = signInAuthorizationURL(start, provider, reauthenticate = true)
            assertEquals(listOf("authkit"), url.getQueryParameters("provider"))
            assertEquals(listOf("0"), url.getQueryParameters("max_age"))
            assertEquals(listOf("sign-in"), url.getQueryParameters("screen_hint"))
            assertEquals("state+fixture", url.getQueryParameter("state"))
            assertEquals("challenge_fixture", url.getQueryParameter("code_challenge"))
        }
    }
}
