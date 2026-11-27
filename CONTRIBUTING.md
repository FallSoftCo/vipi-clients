# Maintaining the source

Start from the private Git checkout and make changes on a review branch. The
[maintainer map](docs/MAINTAINING_VIPI.md) shows which repository and module
owns each part of the product. The [release runbook](docs/HUMAN_RELEASE.md)
covers signing, production and store review separately.

## Set up the local checks

Use Python 3.12, Node 22 with npm, uv, Bash, zsh and Make for the common checks.
Use the checked-in Kotlin and Xcode toolchain instructions when working on the
native apps.

```sh
npm ci --ignore-scripts
make check
```

The lockfile pins the website formatter. Make runs Ruff 0.15.13 and
clang-format 23.1.5 through `uvx`. In an already provisioned environment,
`RUFF` and `CLANG_FORMAT` can point to the same versions installed locally.
No app account or deployment authority is needed for these checks.

## Format and check the code you change

| Area | Apply formatting | Check without editing |
| --- | --- | --- |
| Python services, tests and scripts | `make format-python` | `make check-python` |
| Homepage HTML, CSS and JavaScript | `make format-website` | `make check-website` |
| Android JNI C and C++ | `make format-jni` | `make check-jni-format` |
| Android app, core and tests | `make format-android` | `make check-android-format` |
| Swift app, extension, library and tests | `make format-swift` on the native Mac | `make check-swift-format` on the native Mac |

Keep generated artifacts, vendored sources and historical release archives at
their pinned bytes. Review formatting changes separately from behavior changes.
Use `git diff --check` and review the staged diff before committing. For
formatting-only work on a mature component, compare semantics and run the same
tests you would run for a normal change to that component.

The website formatting command also refreshes content-based asset versions.
New versioned references can start with `?v=0`. When adding or revising public
copy, verify the loopback preview before preparing a publication.

## Run the relevant integration tests

- **Relay.** Run the existing suite with PostgreSQL 16 in a disposable
  socket-only cluster. From an environment with the backend and test libraries
  installed, run `mkdir -p build` and then
  `make test-relay RUN_DIRECTORY=build/pg-qa-001`. The run directory itself
  must be new. Use `PG_BIN=/path/to/postgresql/16/bin` if `pg_config` points
  elsewhere. Use `PYTHON=/path/to/venv/bin/python` if needed. Read the JUnit
  file and original cluster cleanup receipt in the chosen directory.
- **Android.** Use the existing unit and instrumentation commands in the
  [Android guide](docs/ANDROID_MAINTAINER.md). Use a dedicated emulator and
  the isolated test app ID.
- **iOS.** Use the native simulator build and named suites in the
  [iOS guide](docs/IOS_MAINTAINER.md). Retain the `.xcresult` files.
- **Message compatibility.** For changes to delivery, the wire format or
  group membership, use `scripts/test-native-chat-actions.py` from the
  private checkout with dedicated simulators. The loopback fixture exercises
  the real clients and relay using disposable identities. Its synthetic push
  capture and the production handset check cover different behavior.

Record the build commit, fixture scope, result and outstanding verification
when handing off a change. Preserve original results after a timeout and
inspect the current state before deciding whether a new run is safe.
