"""Product information served without trackers, external assets, or browser JS."""
from html import escape

from starlette.responses import HTMLResponse, JSONResponse

from .accounts import normalize_username
from .delivery import DeliveryError

VERSION = "2026-11-18"
COMPANY_PRIVACY = "https://fallsoft.co/privacy-policy"
COMPANY_TERMS = "https://fallsoft.co/terms-of-service"

PAGES = {
    "/": ("Immersive chat with friends.", """
        <p class="lead">Chat with your friends. Read and hear the conversation in the language you want to learn.</p>
        <p>Choose the language you know and the one you want to learn. Vipi translates whole messages on your device. Your friends can keep writing as usual; they do not need to learn the same language.</p>
        <p>Tap a message to hear it. Hold the chat to read in the language you know, then release to return to your practice language. For supported non-Latin scripts, a reading in Latin letters appears by default. Double-tap the chat to switch scripts. You may need to download your selected languages and voices first.</p>
        <p>Chats with friends are end-to-end encrypted. Translation and speech run on your device. Bot mini is an optional separate subscription for chatting with vBot. Messages you send to vBot go to our response provider.</p>
        <p><strong>Vipi is in testing.</strong> App downloads will appear here after store approval. Translations can be wrong; Vipi does not promise a particular level of fluency.</p>
    """),
    "/privacy": ("Vipi privacy", """
        <p class="lead">Your conversations belong to you.</p>
        <p>This product notice explains Vipi's data handling alongside the <a href="https://fallsoft.co/privacy-policy">Fallible Software, Co. privacy policy</a>. Updated November 18, 2026.</p>
        <h2>Conversations with friends</h2>
        <p>Human messages are encrypted on the sender's device and decrypted on the recipient's device using the Signal protocol. Vipi's relay does not have the keys to read their content. Account identifiers, device identifiers, message identifiers, routing, timing, delivery state, and public encryption keys are visible to the service. End-to-end encryption does not hide that metadata.</p>
        <p>Undelivered ciphertext has a 72-hour delivery window measured from the message's creation time. Ciphertext is cleared after a delivery receipt, cancellation, or expiry cleanup. Delivery metadata is removed seven days after that delivery window ends. Cleanup normally runs each minute; an outage can delay cleanup. Your device and your friend's device keep their own history until it is removed there.</p>
        <h2>Language and audio</h2>
        <p>Whole-message translation and reading guides for human messages are prepared locally. Downloads fetch language data, not translations of your conversations. Speech uses the app's local speech engines or supported device voices. Downloaded data, learning preferences, and chat history remain on your device.</p>
        <p>To avoid translating a message repeatedly, Vipi may keep its translation and reading guide in your encrypted local message storage. These copies are not sent to Vipi's servers. The original message is kept separately from its translation.</p>
        <p>Third-party language and notification SDKs can send operational diagnostics such as installation and device identifiers, app and operating-system details, language/model selections, detected language tags, performance, and errors to their providers. Google's on-device ML Kit translation does not send translation input or output to Google. See <a href="https://developers.google.com/ml-kit/terms">ML Kit's terms</a>, its <a href="https://developers.google.com/ml-kit/ios-data-disclosure">Apple-platform disclosures</a> and <a href="https://developers.google.com/ml-kit/android-data-disclosure">Android disclosures</a>, and <a href="https://firebase.google.com/support/privacy">Firebase privacy information</a>. We do not use advertising tracking or sell your chat content.</p>
        <h2>Account, purchases, and notifications</h2>
        <p>WorkOS handles sign-in, including your email address and authentication records. Vipi stores an account identifier, your chosen username and display name, and device registration information. Your email is not exposed through username lookup. People who know your exact username can find your profile.</p>
        <p>Vipi records when your profile was created and when your first 30 days of free access end. These dates are tied to your account, so signing in again or changing devices does not restart the free period. This free access does not create a store subscription or require payment details.</p>
        <p>Apple or Google handles payment details. Vipi receives the purchase information needed to verify subscription access, including product, store transaction or purchase references, expiry, trial, and revocation status. Vipi does not receive your payment card details. Store notification identifiers and content fingerprints are kept for up to 30 days to avoid processing duplicate events; notification bodies and purchase tokens are not included in those receipts.</p>
        <p>For background message delivery, Vipi stores an encrypted push token and uses Apple Push Notification service or Firebase Cloud Messaging. Android registers for background delivery when your account is ready, including when visible notifications are turned off. On iOS, push registration follows your notification permission and Vipi notification setting. Push requests contain a generic notification or inbox-change signal, not the sender's name or message content. The app retrieves and decrypts messages separately. Your device's notification settings control what appears on its screen.</p>
        <h2>Optional vBot</h2>
        <p>vBot is a separate service supplied through DeepSeek. Before you use it, Vipi asks you to consent to sending the recent vBot conversation needed to generate a reply. Human conversations with friends are never included automatically. A request includes up to 12 messages and up to 8,192 bytes of that vBot conversation.</p>
        <p>vBot requests pass through Vipi's server to DeepSeek, so they do not have human-chat end-to-end encryption. Vipi retains request identifiers and usage/cost records, not ordinary prompt and reply text. Vipi is responsible for the handling described in this notice; DeepSeek processes the submitted content under its applicable API terms. DeepSeek's <a href="https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html">general privacy policy</a> describes its own services and excludes downstream apps such as Vipi. We do not promise zero retention by DeepSeek. Avoid sharing sensitive information you do not want that provider to process.</p>
        <h2>Reports and account safety</h2>
        <p>Blocking stops new messages between the blocked accounts. If you choose to report a person or reply, Vipi shows what will be submitted. Only the selected original text and the report's account/message identifiers, reason, and timing are sent for review. This separately shares that selected content with Fallible Software, Co.; the rest of a human conversation remains encrypted.</p>
        <p>Submitted text is encrypted in server storage and can be read by authorized operators for review. Reports expire after 30 days, and account deletion removes reports associated with that account. Account restriction and review records support service safety. Reporting does not itself suspend another account or establish who authored the submitted text.</p>
        <h2>History backups</h2>
        <p>History backup is an explicit export to a location you choose. The app encrypts the file using your backup password before handing it to your selected storage provider. Vipi does not automatically host that file and cannot recover a forgotten backup password. The first backup format includes completed human-message history, not live encryption keys, sign-in credentials, unsent messages, or vBot history.</p>
        <p>Separately, encrypted service backups retain account, device-registration, subscription, usage, and safety records for disaster recovery. They exclude relayed messages, public messaging-key records, push tokens, and submitted report text. We retain up to three verified backup generations, replacing older copies as new backups succeed. This is a count of copies, not a guaranteed number of days.</p>
        <h2>Deletion and retention</h2>
        <p>You can delete your account in the app or through the <a href="/delete-account">account deletion page</a>. Deletion removes the Vipi profile, device and key records, pending messages, subscription access records, usage records, and reports. Your shared Fallsoft sign-in and accounts in other apps remain. A minimal deletion receipt remains for seven days so you can verify completion. A keyed identity hash and the original free-trial dates remain while your shared Fallsoft account exists, solely to prevent deleting and rejoining Vipi from restarting the free period.</p>
        <p>Keyed hashes of billing account identifiers also remain while your shared Fallsoft account exists, so you can restore a purchase after deleting and rejoining Vipi with the same sign-in. These hashes contain no email, raw old profile identifier, purchase token, store transaction, product, expiry, or paid-access record. Restoration requires current verification with Apple or Google; the hashes do not grant access by themselves.</p>
        <p>Deleting your shared Fallsoft sign-in and accounts in other Fallsoft apps is a separate request. Contact <a href="mailto:privacy@fallsoft.co">privacy@fallsoft.co</a> for that request. The Vipi deletion button does not delete those accounts or make that request.</p>
        <p>Earlier encrypted service backups can retain those service records until the copies are replaced or deleted. Recovery must honor account deletions before a restored service is reopened; a backup is not permission to reactivate a deleted account.</p>
        <p>Deleting an account does not cancel an Apple or Google subscription, erase another person's local message history, or delete backup files you saved elsewhere. Cancel subscriptions in the store and manage your own stored copies. Operational providers may retain records they independently need for payment, security, or legal obligations. Contact us about privacy or deletion questions.</p>
        <h2>Who operates Vipi</h2>
        <p>Vipi is operated by Fallible Software, Co. Service hosting is provided by Hetzner; identity by WorkOS; optional push and purchases by Apple and Google; and optional vBot responses by DeepSeek. Processing may occur in countries different from yours. Vipi is not directed to children under 13.</p>
        <p>Privacy contact: <a href="mailto:privacy@fallsoft.co">privacy@fallsoft.co</a>. Product and safety contact: <a href="mailto:one@fallsoft.co">one@fallsoft.co</a>.</p>
    """),
    "/terms": ("Using Vipi", """
        <p class="lead">Real conversations. Respect for the people in them.</p>
        <p>These product terms supplement the <a href="https://fallsoft.co/terms-of-service">Fallible Software, Co. terms of service</a>. Updated November 17, 2026. The separate license supplied with software and language data governs rights to that software and data.</p>
        <h2>Your account and conversations</h2>
        <p>Use your own account, protect your device, and keep any backup password safe. Vipi supports one active messaging device per account. Replacing it changes the device's encryption identity; friends may need to verify the new identity. Vipi does not maintain a cloud copy of your complete chat history.</p>
        <p>Do not use Vipi for threats, harassment, hate, scams, spam, exploitation, sexual content involving minors, nonconsensual intimate material, or other unlawful activity. Do not impersonate others, distribute malware, attack the service, or evade account restrictions. You must have the right to share what you send. Vipi is not for children under 13.</p>
        <p>You can block a person and choose to submit a report. We may restrict accounts after reviewing abuse. Reports are user-submitted evidence, not automatic proof; an account is not suspended merely because someone reported it. For a safety concern or restriction review, contact <a href="mailto:one@fallsoft.co">one@fallsoft.co</a>. Vipi is not an emergency service.</p>
        <h2>Immersion and vBot</h2>
        <p>Translations, transliteration, and pronunciation can be incomplete or wrong. The original message remains available. Vipi provides language exposure during conversation; it does not guarantee fluency, translation accuracy, or suitability for a consequential decision.</p>
        <p>vBot is an optional generated conversation partner, not a person. It can make mistakes. Its use requires separate consent to provider processing described in the <a href="/privacy">Vipi privacy notice</a>. Human messages are not sent to vBot automatically.</p>
        <p>If you are under 18, or under the minimum age required in your country, read these terms and <a href="https://cdn.deepseek.com/policies/en-US/deepseek-terms-of-use.html">DeepSeek's terms</a> with a parent or legal guardian. Use vBot only with their consent. Vipi's minimum age of 13 still applies.</p>
        <h2>Subscriptions and trials</h2>
        <p>Your first 30 days of Vipi are free, starting when you create your Vipi profile. You do not need to start a subscription or provide payment details. Signing in again or changing devices does not restart this period. You will not be charged when it ends. Subscribe if you want to keep sending messages after your free access ends.</p>
        <p>Base and Bot mini are separate annual subscriptions. Bot mini is optional and requires active Base access, including the initial free period. Bot mini may offer an eligible one-month introductory trial; eligibility and the exact renewal date come from the store. Starting Vipi does not enroll you in either subscription.</p>
        <p>Before subscribing, the app and store show the local price, billing period, trial eligibility, and what is included. A subscription renews unless you cancel through the store. Cancel before the store's displayed trial or renewal deadline to avoid the next charge. Manage purchases and refunds through the store that billed you. Deleting Vipi or your account does not cancel a subscription.</p>
        <p>Bot mini includes a displayed monthly reply allowance that resets each calendar month in UTC; unused replies do not roll over. Availability depends on the provider and service capacity. If a request's result is uncertain, the app will not automatically resubmit it and risk a duplicate response or charge.</p>
        <p>Saved local history and history export remain accessible when free or paid access ends. Sending new messages requires active Base access. Using vBot also requires active Bot mini access.</p>
        <h2>Delivery and availability</h2>
        <p>Messages have a 72-hour relay delivery window. Devices can retry within that window when connectivity permits. A message can expire if the recipient remains offline; the relay is not long-term history storage. Vipi does not promise delivery, uninterrupted service, or a particular latency. Keep backups of history you wish to retain.</p>
    """),
    "/help": ("Vipi help", """
        <h2>Start a conversation</h2><p>Try the example, choose the language you know and the one you want to learn, then sign in. Share your exact username with a friend or search for theirs. No address-book upload is needed.</p>
        <h2>Read and listen</h2><p>Vipi translates whole messages into your practice language on your device. Tap a message to hear it in that language; tap it again to stop. Hold the chat to read in the language you know, then release to return to your practice language. Reading guides in Latin letters appear by default for supported scripts. Double-tap the chat to switch between the reading guide and the language's own script.</p>
        <p>Turn on the speaker in the chat header to hear new messages automatically. Turn it off to stop playback. Earlier messages do not start playing when you turn it on. Autoplay also stops when you leave the chat or put Vipi in the background.</p>
        <p>Your selected languages and voices may need a download before first use. If a translation or voice is unavailable, follow the message shown in the app to prepare it or try again. Translation quality varies by language and context.</p>
        <h2>Sign in again</h2><p>If Vipi asks you to sign in again, use the same account to reconnect. Conversations saved on this device stay here. Signing in again does not move your account to a different device.</p>
        <h2>Change your active device</h2><p>Vipi uses one active messaging device at a time. Choosing Use this device is a separate action: it disconnects the other active device and changes your encryption keys. Messages still waiting for delivery cannot move between devices. Review the confirmation before continuing, then compare the new security number with your friends.</p>
        <h2>Missing messages</h2><p>Check connectivity and notification permission, then reopen the conversation to refresh. If a message expires after 72 hours, send a new message when it is still relevant. Replacing your active device can require your friend to verify its new identity.</p>
        <h2>Your first 30 days</h2><p>Start chatting without payment details. Your free access ends 30 days after you create your Vipi profile; the app shows the end date. There is no automatic charge. After that, subscribe to keep sending messages. You can still read and export your saved local history.</p>
        <h2>Subscriptions</h2><p>Use <a href="https://apps.apple.com/account/subscriptions">Apple subscription settings</a> or <a href="https://play.google.com/store/account/subscriptions">Google Play subscription settings</a> to manage or cancel a plan you chose to purchase. Base and the optional Bot mini plan are separate. Bot mini has its own store trial for eligible subscribers; it does not start automatically.</p>
        <h2>History and your account</h2><p>Use History backup in Settings to save an encrypted file. Keep the password separately; it cannot be reset by Vipi. Restore under the same Vipi account. Backups do not restore live encryption keys or unsent messages.</p><p><a href="/delete-account">Delete your account</a>. This does not cancel a subscription or remove copies kept by friends or in your own backup storage.</p>
        <h2>Contact</h2><p>Product and safety: <a href="mailto:one@fallsoft.co">one@fallsoft.co</a>. Privacy: <a href="mailto:privacy@fallsoft.co">privacy@fallsoft.co</a>. Do not email passwords or your private conversation history. To report a message in the app, select that message and review the content before submitting.</p>
    """),
}


def install(app):
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
        headers = {"Cache-Control":"no-store", "Referrer-Policy":"no-referrer",
            "X-Content-Type-Options":"nosniff", "X-Frame-Options":"DENY",
            "Content-Security-Policy":"default-src 'none'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'",
            "Permissions-Policy":"camera=(), microphone=(), geolocation=()"}
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
            <p>Chat with your friend while reading the conversation in the language you want to learn. Vipi translates whole messages on your device. Tap a message to hear it, or hold the chat to read in the language you know.</p>
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
            <p>Conversations with friends are end-to-end encrypted. You don't need to upload your contacts or use vBot.</p>
        """, private_link=True)
    for path, (title, body) in PAGES.items():
        # Factory keeps route signatures free of user-overridable default fields.
        def endpoint(title=title, body=body):
            async def get_page():
                return render(title, body)
            return get_page
        app.add_api_route(path, endpoint(), methods=["GET"], include_in_schema=False)
