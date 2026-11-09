Root review correction r03, before any Android execution. Original r01/r02 freezes and files remain unchanged.

The sidecar negative controls now copy the actual valid pack before adding each sidecar. The previous empty-file control could fail the pack hash independently and did not prove sidecar handling. ADB package checks now pass one fixed shell command argument, avoiding nested shell quoting ambiguity.

The runner additionally enforces a conservative 1,900,000,000-byte total filesystem free-space drop from its initial prepare baseline, plus the task-only 4GiB floor. This can also detect unrelated disk consumption and does not attribute that consumption to this task. Existing full-peak admission, time/output limits, isolated package and one-submission receipts are retained.

Root reviewed the frozen reader/tokenizer, source extractor, model binding, instrumentation, Gradle configuration and verifier. Debug qualification precedes authorization of optimized R8 execution. The existing pocket_verify_api35/5620 AVD may be booted once under a separate bounded root-owned launcher; no other device, ADB server, application or system setting is changed.
