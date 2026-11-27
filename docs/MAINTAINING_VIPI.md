# Maintaining Vipi

Use the private integrated Git source for development. Keep the exact commit
for every build, test or publication receipt. Start with the
[release runbook](HUMAN_RELEASE.md) when preparing anything for a store or
production. Use the [contributor guide](../CONTRIBUTING.md) for local formatting
and integration checks.

## Get the correct source

| Source | What it owns |
| --- | --- |
| Private integrated Vipi repository | The full native apps, relay, shared data, test fixtures and landing-page source. The verified store-candidate baseline is `release/native-store-candidate-20261127` at `1e12989740301dfd6e46caee6ad284b7a2421bd4`. The existing checkouts on system76 and the native Mac use the private release history. |
| Public `FallSoftCo/vipi-clients` | Client source publication. Use its source manifest when checking correspondence to a signed client. Use the private integrated repository for backend or coordinated product development. |
| Private `FallSoftCo/infrastructure` | Serving unit definitions, host and ingress configuration, reviewed deployment tools and receipts. Track the published Vipi production release ref and the current independent host record. |
| Private `FallSoftCo/vipi-marketing` | Studio, campaign drafts, carousel tooling and marketing release source. Preserve local drafts, the owned signing identity and the current installation when testing updates. |

On the native Mac the existing checkout is under
`/Users/Apple/Development/vipi-integrated-20261126`. The private baseline is
available to the owner through the pinned host alias at
`ssh://fallsoft-production/srv/fallsoft/staging/vipi-source-recovery-20261107/working`.
Use the owner SSH identity and the [access guide](RELEASE_ACCESS.md) if the
connection needs a refresh. Use the portable private handoff bundle to
recover the review ref when it is missing from a checkout with the baseline.

From an existing private checkout, compare the intended branch with its
approved upstream before creating a clean working branch.

```sh
git status --short
git remote -v
git ls-remote origin refs/heads/release/native-store-candidate-20261127
VIPI_BASELINE=1e12989740301dfd6e46caee6ad284b7a2421bd4
git worktree add -b work/description /path/to/vipi-worktree "$VIPI_BASELINE"
```

The named branch and hash above are a verified baseline, retained for
reproduction. Use the release record for later candidate selection. Preserve
uncommitted work in other checkouts. Keep private deployment code, credentials
and test records out of the public client history.

## Operate the website, Studio and relay

The following private source revisions were verified for this handoff. Use the
release record to select later revisions and compare them with the current
running services and downloads.

| Component | Runbook |
| --- | --- |
| Production relay | [Human backend operations](https://github.com/FallSoftCo/infrastructure/tree/2a7ab588d4c34f77097bcb50b8aeb63091f7f38f/services/vipi-relay/human-operations) includes rebuilding the runtime, isolated qualification, launch boundaries, retention and recovery. |
| Private relay standby | [Human standby operations](https://github.com/FallSoftCo/infrastructure/tree/31545935efe067a5afde0a5898a4d4704634d00e/services/vipi-relay/ops/human-standby) covers exact source, signatures, installation steps and original-effect checks. |
| Studio and website | [Studio and website maintenance](https://github.com/FallSoftCo/vipi-marketing/blob/fec22ea62cfffd690e96e301458c5c233c00c734/docs/STUDIO_MAINTAINER.md) covers local development, release signing, feed and alert recovery, creative drafts and website publication. |

## Build and verify a change

- [Android development, QA and Play](ANDROID_MAINTAINER.md)
- [iOS development, QA and TestFlight](IOS_MAINTAINER.md)
- [Backend architecture](ARCHITECTURE.md),
  [chat relay contract](CHAT_FEATURES_RELAY.md), and the host runbooks in
  private `FallSoftCo/infrastructure`
- [Sign-in and credential recovery](RELEASE_ACCESS.md)
- [Current build environments](BUILD_ENVIRONMENTS.md) for toolchains and
  historical source receipts
- [Verification ledger](VERIFICATION.md) for test scope and unresolved
  release checks

| Change | Start here |
| --- | --- |
| iOS signed-in startup and recovery | `ios/Vipi/ConnectedChatRoot.swift` owns chat startup, profile setup and device replacement. |
| iOS chat header, per-chat language and accessibility | `ios/Vipi/ImmersionModeToggle.swift`, `ConversationLanguages.swift`, `ConnectedChatView.swift` and `GroupsViews.swift` |
| Android chat, vocabulary practice and language settings | [Android maintainer guide](ANDROID_MAINTAINER.md) and `android/app/src/main/java/co/fallsoft/vipi` |
| Local voice data, supported codes and model preparation | [Local language support](LOCAL_LANGUAGE_SUPPORT.md), `scripts/build-android-speech-data.py` and the shared voice manifest under `android/app/src/main/assets/speech` |
| Encrypted delivery, capability negotiation and old-client compatibility | `backend/vipi/api.py` assembles the service. `messages_api.py` registers message HTTP endpoints and `api_inputs.py` validates incoming request bodies. Keep delivery rules in the inbox and delivery modules. [Chat relay contract](CHAT_FEATURES_RELAY.md) |
| Landing page walkthrough | `release/marketing-homepage/demo-conversation.js` for the 50 messages, `app.js` for conversation playback, `fish-school.js` for background motion, `waitlist.js` for signup and campaign attribution, and `index.html` for page copy |
| Bluesky and Instagram draft tooling | Private `FallSoftCo/vipi-marketing` repository |

## Review boundaries

Place screen-specific UI with its screen. Keep network, encryption,
persistence and delivery behavior in the existing model or service that owns
their lifecycle. Use existing native components or move their implementation
before adding a second state owner. Preserve configuration, compatibility and
provider behavior when reorganizing code.

Translation capability, offline voice selection and readable transliteration are
separate checks. Clients share the voice manifest with the canonical language
and engine identifiers. Keep native playback and translation logic on each
platform. Update both native eligibility lists if a script-reading route changes.

The native messaging journey uses real app crypto and synthetic accounts. Extend
that journey when a change affects interchange. Use focused native tests for
gestures and accessibility. These results complement listening and installation
checks on a physical device.

For a change, record the baseline, the tests that exercise its normal entry
points and the observed result at the final commit. Reuse focused regression
coverage. Add a test when an important change lacks an assertion in the
existing suites. Inspect private fixtures and names before running their
commands against any device or service.

The original service setup and in-place upgrade scripts in `ops` document
historical release paths. Use the current scoped release packet to plan a live
API, schema or worker change. Verify compatibility and existing accepted work
before replacing a service generation.

The static website can be previewed with `python3 -m http.server` from its
directory. Its browser entry point is `app.js`. From the repository root, run
`make format-website` to format the source and refresh the content versions
in the module imports and HTML entry page. `make check-website` verifies both.
A website content edit can change the story independently of the animation
code. Publishing and store actions are recorded separately from source commits.
