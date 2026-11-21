"""Product information served without trackers, external assets, or browser JS."""
from html import escape
from pathlib import Path

from starlette.responses import HTMLResponse, JSONResponse, Response

from .accounts import normalize_username
from .delivery import DeliveryError

VERSION = "2026-11-20"
COMPANY_PRIVACY = "https://fallsoft.co/privacy-policy"
COMPANY_TERMS = "https://fallsoft.co/terms-of-service"

LEGAL_DIRECTORY = Path(__file__).with_name("legal")
LEGAL_DOCUMENTS = {
    "/privacy": ("Vipi Privacy Notice", (LEGAL_DIRECTORY / "privacy.html").read_text(encoding="utf-8")),
    "/terms": ("Vipi Terms of Service", (LEGAL_DIRECTORY / "terms.html").read_text(encoding="utf-8")),
}


PAGES = {
    "/": ("Immersive chat with friends.", """
        <p class="lead">Chat with your friends. Read and hear the conversation in the language you want to learn.</p>
        <p>Choose your practice language. Start with one new word at a time, or tap the switch at the top of a chat to read whole messages in that language. Your friend can write as usual.</p>
        <p>Tap a message to hear the practice language. Hold the chat to see the original. For supported scripts, you can read in Latin letters and double-tap to switch scripts. You may need to download the languages and voices first.</p>
        <p>Messaging friends is free. Your chats are end-to-end encrypted, and translation and speech run on your device.</p>
        <p><strong>Vipi is in testing.</strong> App downloads will appear here after store approval. Translations can be wrong; Vipi does not promise a particular level of fluency.</p>
    """),
    **LEGAL_DOCUMENTS,
    "/help": ("Vipi help", """
        <h2>Start a conversation</h2><p>Try the example, choose the language you know and the one you want to learn, then sign in. Tap New chat and choose someone you’ve chatted with before. To connect for the first time, enter their exact Vipi username or share your invite link.</p>
        <p>To invite someone by text or email, choose Invite a friend. You can pick from your phone contacts if you want. Review the draft, then send it from your messaging or mail app.</p>
        <h2>Read and listen</h2><p>Use the switch at the top of a chat to choose Shallow or Deep. In Shallow, a message can introduce one practice word and repeat words you have already seen. In Deep, you see the whole message in your practice language. Tap the message to hear the word or sentence. Hold the chat to see the original. Double-tap to switch between a reading in Latin letters and the original script where available.</p>
        <p>Tap the autoplay control at the top of the chat to turn it on or off. Earlier messages do not start playing when you turn it on. Autoplay stops when you leave the chat or put Vipi in the background.</p>
        <p>Your selected languages and voices may need a download before first use. If a translation or voice is unavailable, follow the message shown in the app to prepare it or try again. Translation quality varies by language and context.</p>
        <h2>Sign in again</h2><p>If Vipi asks you to sign in again, use the same account to reconnect. Conversations saved on this device stay here. Signing in again does not move your account to a different device.</p>
        <h2>Change your active device</h2><p>Vipi uses one active messaging device at a time. Choosing Use this device is a separate action: it disconnects the other active device and changes your encryption keys. Messages still waiting for delivery cannot move between devices. Review the confirmation before continuing, then compare the new security number with your friends.</p>
        <h2>Message status</h2><p>One check means Vipi accepted your message. Two checks mean it reached your friend’s device. The checks change color when a compatible version of Vipi confirms that the message appeared on your friend's screen.</p>
        <h2>Missing messages</h2><p>Check connectivity and notification permission, then reopen the conversation to refresh. If a message expires after 72 hours, send a new message when it is still relevant. Replacing your active device can require your friend to verify its new identity.</p>
        <h2>Free chat</h2><p>Chatting with friends is free. You can start without payment details. If you subscribed in an earlier version, check the subscription in your App Store or Google Play account to manage renewal. Deleting Vipi does not cancel an existing store subscription.</p>
        <h2>History and your account</h2><p>Use History backup in Settings to save an encrypted file. Keep the password separately; it cannot be reset by Vipi. Restore under the same Vipi account. Backups do not restore live encryption keys or unsent messages.</p><p><a href="/delete-account">Delete your account</a>. This does not remove copies kept by friends or in your own backup storage.</p>
        <h2>Contact</h2><p>Product and safety: <a href="mailto:one@fallsoft.co">one@fallsoft.co</a>. Privacy: <a href="mailto:privacy@fallsoft.co">privacy@fallsoft.co</a>. Do not email passwords or your private conversation history. To report a message in the app, select that message and review the content before submitting.</p>
    """),
}


PAGE_HEADERS = {"Cache-Control":"no-store", "Referrer-Policy":"no-referrer",
    "X-Content-Type-Options":"nosniff", "X-Frame-Options":"DENY",
    "Content-Security-Policy":"default-src 'none'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'",
    "Permissions-Policy":"camera=(), microphone=(), geolocation=()"}


def install(app):
    @app.api_route("/vipi-legal.css", methods=["GET", "HEAD"], include_in_schema=False)
    async def legal_stylesheet():
        return Response((LEGAL_DIRECTORY / "vipi-legal.css").read_bytes(), media_type="text/css", headers=PAGE_HEADERS)

    @app.get("/.well-known/apple-app-site-association", include_in_schema=False)
    async def apple_app_links():
        return JSONResponse({"applinks": {"details": [{
            "appIDs": ["3TNL2455JT.co.fallsoft.vipi"],
            "components": [{"/": "/invite/*", "comment": "Open a friend invitation in Vipi"}],
        }]}}, headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/.well-known/assetlinks.json", include_in_schema=False)
    async def android_app_links():
        # Play app-signing certificate independently verified from the retained
        # Play-generated APK. The upload/debug certificates do not authorize links.
        return JSONResponse([{
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {"namespace": "android_app", "package_name": "co.fallsoft.vipi",
                "sha256_cert_fingerprints": ["42:58:FE:AF:D4:BF:C9:EE:88:5D:A6:F1:FF:CE:AE:6A:BF:98:C0:03:93:04:C2:29:1F:D3:E6:23:0A:DB:EF:82"]},
        }], headers={"Cache-Control": "public, max-age=3600"})

    def render(title, body, *, status_code=200, private_link=False):
        html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="light dark">'
            f'<title>{escape(title)} · Vipi</title><link rel="stylesheet" href="/delete-account/style.css"></head>'
            '<body><main><a class="brand" href="/" aria-label="Vipi home">vipi<span>●</span></a>'
            f'<h1>{escape(title)}</h1>{body}</main><footer><nav aria-label="Product information">'
            '<a href="/help">Help</a> · <a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> · '
            '<a href="/delete-account">Delete account</a></nav><p>Vipi · Fallible Software, Co.</p></footer></body></html>')
        headers = dict(PAGE_HEADERS)
        if private_link:
            headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return HTMLResponse(html, status_code=status_code, headers=headers)

    @app.get("/invite/{username}", include_in_schema=False)
    async def friend_invitation(username: str):
        # An invitation carries only the name chosen by its sender. Do not turn
        # this public page into an account-existence or profile lookup endpoint.
        try:
            name = normalize_username(username)
        except DeliveryError:
            return render("This invitation isn't valid", "<p>Ask your friend to share a new invitation from Vipi.</p>",
                status_code=404, private_link=True)
        return render("Chat with me on Vipi", f"""
            <p class="lead">Find your friend with the username <strong>@{escape(name)}</strong>.</p>
            <p>Chat with your friend in your practice language. Switch between one word at a time and the whole message. Tap a message to hear it, or hold the chat to see the original.</p>
            <h2>Already have Vipi?</h2>
            <p><a class="button" href="co.fallsoft.vipi://invite/{escape(name)}">Open Vipi</a></p>
            <p>The invitation opens with your friend's username filled in. Tap Find friend to start your conversation.</p>
            <p>If the app doesn't open:</p>
            <ol><li>Open Vipi and tap New chat.</li>
            <li>Enter <strong>{escape(name)}</strong> in the username field.</li>
            <li>Find your friend and send a message.</li></ol>
            <h2>New to Vipi?</h2>
            <p>Vipi is in testing. App downloads will appear on the <a href="/">Vipi homepage</a> after store approval.</p>
            <p>When the app is available, choose your languages, create your account, then use the username above to start chatting.</p>
            <p>Conversations with friends are end-to-end encrypted. You don't need to upload your contacts or pay to chat.</p>
        """, private_link=True)
    for path, (title, body) in PAGES.items():
        # Factory keeps route signatures free of user-overridable default fields.
        def endpoint(title, body, legal_document):
            async def get_page():
                if legal_document:
                    return HTMLResponse(body, headers=PAGE_HEADERS)
                return render(title, body)
            return get_page
        methods = ["GET", "HEAD"] if path in LEGAL_DOCUMENTS else ["GET"]
        app.add_api_route(path, endpoint(title, body, path in LEGAL_DOCUMENTS), methods=methods, include_in_schema=False)
