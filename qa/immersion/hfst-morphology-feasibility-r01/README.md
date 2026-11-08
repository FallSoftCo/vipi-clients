# Finite-state morphology feasibility

HFST and Apertium were previously source audits only. This capsule records an
actual isolated desktop compilation and lookup of the pinned Swahili morphology
source. It does not enable a language pack or a native runtime dependency.

HFST 3.16.0 and lexd 1.3.1 were extracted from checksum-pinned Ubuntu packages
into a private research directory, without a system installation. The source is
the unchanged `apertium-swa` revision
`4d2e6b6714e8fa2eaa3f3d74686ec683b8ee9890`. Package hashes, licenses, scripts,
input freeze and exact outputs are retained. The scripts record the original
private evidence paths; adapt those paths explicitly for a new reproduction.

The unflagged compiler exhausted its 1 GiB address-space limit. The documented
`lexd -f` mode then compiled the same source in 1.68 seconds with 43,480 KiB peak
RSS. The resulting optimized analyzer is 1,276,945 bytes and generator 933,641
bytes. Forty-two word lookups took 17.7 ms including process startup. A separate
4,200-query batch took 216 ms and 17,560 KiB peak RSS, with exact repeated-output
parity. These are desktop process measurements, not phone latency or incremental
application memory.

The relation recognizes `mtu/watu`, `kiti/viti`, and tense/person forms such as
`ninasoma/nilisoma/nitasoma`. Generation and analysis use the same relation in
opposite directions. This supports testing morphology as a source of constraints
for phrase slots or as a build-time form generator.

The retained language data is not safe to activate generally. It misses
`kitabu/vitabu`, treats `chakula` only as a verb, misses common irregular forms,
generates `sisoma` where the diagnostic expects `sisomi`, and labels
`hamtasoma` with the wrong person. Multiple analyses are retained. Feature
presence was 33/42 and expected generation 8/12 on authored diagnostics; neither
count measures linguistic precision or conversation coverage.

The pipeline deliberately omits upstream spelling relaxation and sentence
disambiguation. Morphology does not settle which meaning of a word belongs in a
sentence, nor does it supply a complete bilingual translation. The native
phrase/template comparison remains a separate experiment. Any later adoption
must demonstrate useful gain, source-range preservation, ambiguity handling,
native resource costs and corresponding-source requirements.

Primary references: [HFST distribution](https://hfst.github.io/downloads/index.html),
[lexd](https://github.com/apertium/lexd),
[Apertium morphology](https://wiki.apertium.org/wiki/Morphological_dictionary),
and the [pinned Swahili source](https://github.com/apertium/apertium-swa/tree/4d2e6b6714e8fa2eaa3f3d74686ec683b8ee9890).
