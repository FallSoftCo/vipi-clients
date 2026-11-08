"""Product information served without trackers, external assets, or browser JS."""
from html import escape

from starlette.responses import HTMLResponse

VERSION = "2026-11-08"
COMPANY_PRIVACY = "https://fallsoft.co/privacy-policy"
COMPANY_TERMS = "https://fallsoft.co/terms-of-service"

PAGES = {
    "/": ("A little more language, in every conversation.", """
        <p class="lead">Vipi brings another language into the conversations you already care about.</p>
        <p>Choose an immersion language. Familiar words and phrases gradually alternate with their translations, right inside a message. Keep the original close, reveal the whole translation, and listen when you want to hear it.</p>
        <p>Chat with friends using end-to-end encryption. Language matching, translation, and speech run on your device after the needed language data is available. The optional vBot is a separate conversation partner with separate data sharing.</p>
        <p><strong>Vipi is in testing.</strong> App downloads will appear here after store approval. Translations can be wrong; Vipi does not promise a particular level of fluency.</p>
    """),
    "/privacy": ("Vipi privacy", """
        <p class="lead">Your conversations belong to you.</p>
        <p>This product notice explains Vipi's data handling alongside the <a href="https://fallsoft.co/privacy-policy">Fallible Software, Co. privacy policy</a>. Updated November 8, 2026.</p>
        <h2>Conversations with friends</h2>
        <p>Human messages are encrypted on the sender's device and decrypted on the recipient's device using the Signal protocol. Vipi's relay does not have the keys to read their content. Account identifiers, device identifiers, message identifiers, routing, timing, delivery state, and public encryption keys are visible to the service. End-to-end encryption does not hide that metadata.</p>
        <p>Undelivered ciphertext has a 72-hour delivery window measured from the message's creation time. Ciphertext is cleared after a delivery receipt, cancellation, or expiry cleanup. Delivery metadata is removed seven days after that delivery window ends. Cleanup normally runs each minute; an outage can delay cleanup. Your device and your friend's device keep their own history until it is removed there.</p>
        <h2>Language and audio</h2>
        <p>Immersion lookup and translation of human messages happen locally. Downloads fetch language data, not translations of your conversations. Speech uses the app's local speech engines or supported device voices. Downloaded data, learning preferences, and chat history remain on your device.</p>
        <p>Third-party language and notification SDKs can send operational diagnostics such as installation and device identifiers, app and operating-system details, language/model selections, performance, and errors to their providers. Google's on-device ML Kit translation does not send translation input or output to Google. See <a href="https://developers.google.com/ml-kit/terms">ML Kit's terms</a>, its <a href="https://developers.google.com/ml-kit/ios-data-disclosure">Apple-platform disclosures</a> and <a href="https://developers.google.com/ml-kit/android-data-disclosure">Android disclosures</a>, and <a href="https://firebase.google.com/support/privacy">Firebase privacy information</a>. We do not use advertising tracking or sell your chat content.</p>
        <h2>Account, purchases, and notifications</h2>
        <p>WorkOS handles sign-in, including your email address and authentication records. Vipi stores an account identifier, your chosen username and display name, and device registration information. Your email is not exposed through username lookup. People who know your exact username can find your profile.</p>
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
        <p>You can delete your account in the app or through the <a href="/delete-account">account deletion page</a>. Deletion removes the Vipi profile, device and key records, pending messages, subscription access records, usage records, and reports, and schedules removal of the WorkOS identity. A minimal deletion receipt remains for seven days after provider cleanup finishes so you can verify completion.</p>
        <p>Earlier encrypted service backups can retain those service records until the copies are replaced or deleted. Recovery must honor account deletions before a restored service is reopened; a backup is not permission to reactivate a deleted account.</p>
        <p>Deleting an account does not cancel an Apple or Google subscription, erase another person's local message history, or delete backup files you saved elsewhere. Cancel subscriptions in the store and manage your own stored copies. Operational providers may retain records they independently need for payment, security, or legal obligations. Contact us about privacy or deletion questions.</p>
        <h2>Who operates Vipi</h2>
        <p>Vipi is operated by Fallible Software, Co. Service hosting is provided by Hetzner; identity by WorkOS; optional push and purchases by Apple and Google; and optional vBot responses by DeepSeek. Processing may occur in countries different from yours. Vipi is not directed to children under 13.</p>
        <p>Privacy contact: <a href="mailto:privacy@fallsoft.co">privacy@fallsoft.co</a>. Product and safety contact: <a href="mailto:one@fallsoft.co">one@fallsoft.co</a>.</p>
    """),
    "/terms": ("Using Vipi", """
        <p class="lead">Real conversations. Respect for the people in them.</p>
        <p>These product terms supplement the <a href="https://fallsoft.co/terms-of-service">Fallible Software, Co. terms of service</a>. Updated November 7, 2026. The separate license supplied with software and language data governs rights to that software and data.</p>
        <h2>Your account and conversations</h2>
        <p>Use your own account, protect your device, and keep any backup password safe. Vipi supports one active messaging device per account. Replacing it changes the device's encryption identity; friends may need to verify the new identity. Vipi does not maintain a cloud copy of your complete chat history.</p>
        <p>Do not use Vipi for threats, harassment, hate, scams, spam, exploitation, sexual content involving minors, nonconsensual intimate material, or other unlawful activity. Do not impersonate others, distribute malware, attack the service, or evade account restrictions. You must have the right to share what you send. Vipi is not for children under 13.</p>
        <p>You can block a person and choose to submit a report. We may restrict accounts after reviewing abuse. Reports are user-submitted evidence, not automatic proof; an account is not suspended merely because someone reported it. For a safety concern or restriction review, contact <a href="mailto:one@fallsoft.co">one@fallsoft.co</a>. Vipi is not an emergency service.</p>
        <h2>Immersion and vBot</h2>
        <p>Translations, transliteration, and pronunciation can be incomplete or wrong. The original message remains available. Vipi provides language exposure during conversation; it does not guarantee fluency, translation accuracy, or suitability for a consequential decision.</p>
        <p>vBot is an optional generated conversation partner, not a person. It can make mistakes. Its use requires separate consent to provider processing described in the <a href="/privacy">Vipi privacy notice</a>. Human messages are not sent to vBot automatically.</p>
        <h2>Subscriptions and trials</h2>
        <p>Base and Bot mini are separate annual subscriptions. Bot mini is optional and requires active Base access. Each may offer an eligible one-month introductory trial; eligibility and the exact renewal date come from the store. Starting Base does not enroll you in Bot mini.</p>
        <p>Before subscribing, the app and store show the local price, billing period, trial eligibility, and what is included. A subscription renews unless you cancel through the store. Cancel before the store's displayed trial or renewal deadline to avoid the next charge. Manage purchases and refunds through the store that billed you. Deleting Vipi or your account does not cancel a subscription.</p>
        <p>Bot mini includes a displayed monthly reply allowance that resets each calendar month in UTC; unused replies do not roll over. Availability depends on the provider and service capacity. If a request's result is uncertain, the app will not automatically resubmit it and risk a duplicate response or charge.</p>
        <p>Saved local history and history export remain accessible when subscription access ends. Sending new messages and using paid service features requires the applicable active subscription.</p>
        <h2>Delivery and availability</h2>
        <p>Messages have a 72-hour relay delivery window. Devices can retry within that window when connectivity permits. A message can expire if the recipient remains offline; the relay is not long-term history storage. Vipi does not promise delivery, uninterrupted service, or a particular latency. Keep backups of history you wish to retain.</p>
    """),
    "/help": ("Vipi help", """
        <h2>Start a conversation</h2><p>Choose your native and immersion languages, prepare their language data, and sign in. Share your exact username with a friend or search for theirs. No address-book upload is needed.</p>
        <h2>Read at your own pace</h2><p>Words and phrases alternate in place while their space stays stable. Pause the alternation, reveal the original, view the whole translation, or listen. For supported scripts, letter guides help you recognize unfamiliar writing; use Listen for pronunciation, and switch back to the original script whenever you want. Translation quality varies by language and context.</p>
        <h2>Missing messages</h2><p>Check connectivity and notification permission, then reopen the conversation to refresh. If a message expires after 72 hours, send a new message when it is still relevant. Replacing your active device can require your friend to verify its new identity.</p>
        <h2>Subscriptions</h2><p>Use <a href="https://apps.apple.com/account/subscriptions">Apple subscription settings</a> or <a href="https://play.google.com/store/account/subscriptions">Google Play subscription settings</a> to manage or cancel the plan purchased there. Base and the optional Bot mini plan are separate.</p>
        <h2>History and your account</h2><p>Use History backup in Settings to save an encrypted file. Keep the password separately; it cannot be reset by Vipi. Restore under the same Vipi account. Backups do not restore live encryption keys or unsent messages.</p><p><a href="/delete-account">Delete your account</a>. This does not cancel a subscription or remove copies kept by friends or in your own backup storage.</p>
        <h2>Contact</h2><p>Product and safety: <a href="mailto:one@fallsoft.co">one@fallsoft.co</a>. Privacy: <a href="mailto:privacy@fallsoft.co">privacy@fallsoft.co</a>. Do not email passwords or your private conversation history. To report a message in the app, select that message and review the content before submitting.</p>
    """),
}


def install(app):
    def render(title, body):
        html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="light dark">'
            f'<title>{escape(title)} · Vipi</title><link rel="stylesheet" href="/delete-account/style.css"></head>'
            '<body><main><a class="brand" href="/" aria-label="Vipi home">vipi<span>●</span></a>'
            f'<h1>{escape(title)}</h1>{body}</main><footer><nav aria-label="Product information">'
            '<a href="/help">Help</a> · <a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> · '
            '<a href="/delete-account">Delete account</a></nav><p>Vipi · Fallible Software, Co.</p></footer></body></html>')
        return HTMLResponse(html, headers={"Cache-Control":"no-store", "Referrer-Policy":"no-referrer",
            "X-Content-Type-Options":"nosniff", "X-Frame-Options":"DENY",
            "Content-Security-Policy":"default-src 'none'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'",
            "Permissions-Policy":"camera=(), microphone=(), geolocation=()"})
    for path, (title, body) in PAGES.items():
        # Factory keeps route signatures free of user-overridable default fields.
        def endpoint(title=title, body=body):
            async def get_page():
                return render(title, body)
            return get_page
        app.add_api_route(path, endpoint(), methods=["GET"], include_in_schema=False)
