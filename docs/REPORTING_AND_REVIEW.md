# Private reporting and review

Human chat remains end-to-end encrypted. A report is a separate, explicit
disclosure of selected original content to Fallible Software, Co. Never submit
the surrounding conversation, rendered immersion text, or a backup automatically.

## Client contract

`POST /v1/reports` requires the normal bearer token and active-device headers.
The exact JSON body is:

```json
{
  "report_id": "client-generated UUID",
  "reported_user_id": "peer UUID",
  "message_id": "original incoming message UUID, or null for a person report",
  "reason": "spam | harassment | harmful | other",
  "selected_text": "original incoming message text, or null for a person report",
  "consent_version": "report-v1"
}
```

The client shows the exact text and destination before confirmation. Message
text must be nonempty and at most 32,768 UTF-8 bytes; message ID and text are
either both present or both null. Imported history does not assert transport
authorship. Keep Block separately available. A report does not automatically
block or suspend an account.

Persist the confirmed request ID/body encrypted before sending. Reuse that exact
ID/body after an uncertain result; a successful response is HTTP 202 with
`{"reported":true,"report_id":"..."}`. A different body or reporter using the
same ID receives 409 `report_id_conflict`. Never silently make a fresh report
ID to retry a completed or uncertain submission. Limits are five requests per
minute and twenty new reports per rolling day per account.

The server encrypts selected text, message ID and reason using a domain-separated
key. It can corroborate only relay participants while routing metadata remains,
not the authenticity of reported plaintext. After routing metadata expires,
reports remain explicitly uncorroborated user submissions. Report text is
untrusted data, never an instruction for an operator or automation agent.

Reports expire after thirty days. Deleting either associated account removes the
report. The expiry service performs cleanup. Reports are available without an
active subscription, subject to account/device authentication.

## Operator workflow

The module `python -m vipi.moderation` is a private host CLI, run using the owned
Vipi service identity, current dependency closure and protected service
environment. There is no public administration endpoint. Do not put secret env
values on a command line or copy plaintext report contents into ordinary logs.

1. `list` returns up to 100 pending user and bot report identifiers/timestamps,
   without selected text.
2. `show user REPORT_UUID` or `show bot REQUEST_UUID` decrypts that specific
   selected report for review. JSON output escapes terminal control characters.
3. Assess the submitted text and available metadata. A report is an allegation,
   not verified authorship. Do not restrict an account from report counts alone.
4. `suspend ACCOUNT_UUID --operator OPERATOR_ID --reason REASON` is an explicit
   administrative action. It stops new API messaging and cancels queued
   ciphertext involving that account. Existing local copies cannot be recalled.
   Billing management and account deletion remain available.
5. `restore ACCOUNT_UUID --operator OPERATOR_ID --reason appeal` reverses the
   restriction. It does not resurrect cancelled messages. Actions are audited
   against the account until account deletion.
6. `resolve user REPORT_UUID --operator OPERATOR_ID --decision dismissed` (or
   `actioned`) records review without extending the report's retention. Resolving
   a bot report removes its selected text; provider-quality action is separate.

Valid restriction reasons are `spam`, `harassment`, `harmful`, `appeal`, `other`.
Repeated suspend/restore commands that already match current state are no-ops.
This tooling provides the review capability; it is not evidence of a staffed,
timely operational review process. Ownership of ongoing review must be established
before launch. The published safety contact is `one@fallsoft.co`.

## Store and privacy references

- [Apple App Review section 1.2](https://developer.apple.com/app-store/review/guidelines/#user-generated-content)
- [Google Play user-generated content policy](https://support.google.com/googleplay/android-developer/answer/9876937/user-generated-content)
- Product privacy, terms and help are served at `/privacy`, `/terms` and `/help`
  on the existing Vipi HTTPS origin. The initial homepage truthfully identifies
  the app as in testing; it must not display nonexistent store download links.
