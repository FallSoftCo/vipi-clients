# Read-only profile snapshot comparison

Retained QA pre/post speech-run encrypted profile snapshots were decrypted in memory on the existing emulator with its already-present Android Keystore key. The test reports field names and equality only: id, username and display_name all match. Other encrypted private records match byte-for-byte across those snapshots. Prior message database logical dumps matched and passed integrity checks. Both accounts’ private files matched byte-for-byte before versus after this comparison. No credential plaintext, live network request, account write, restore or key creation was involved. Unchanged auth ciphertext does not prove a fresh server authentication.

ChatSession.open writes the profile again even when it loads unchanged, and PrivateRecords.write uses a fresh GCM IV. This is consistent with the changed ciphertext; the comparison does not establish an external authentication event.
