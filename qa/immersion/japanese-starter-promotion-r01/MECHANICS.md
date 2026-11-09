# Native mechanics and retained failures

The original 46-entry candidate passed actual-route qualification on both clients before the semantic correction. All 384 selected span arrays matched, including source/target text, readings and UTF-16 geometry. Its three known states produced 101, 96 and 0 nonempty messages. The final 45-entry result is documented separately in RESULT.md.

The actual-route smoke verifies `music` through the starter partial, `hello` through the existing authored reference, and a code literal remaining untouched. Every nonempty repeat was cached. Null/unavailable repeats were recorded without claiming reuse; separate repeat latency was not measured. Caller-known snapshots are not evidence of durable vocabulary progression.

Two invalid Android captures remain private: the first stopped on an incorrect unconditional repeat-cache assertion, and the second returned STALE because the harness omitted message-language registration. Neither is acceptance evidence. The corrected caller registers language through the existing API and gates collection on the actual-route smoke. All algorithm and data inputs remained unchanged through those harness repairs.

Every multiword entry requires nonempty whitespace-only inter-token gaps. Punctuation cannot bridge a source unit; newline/tab-only line wrapping remains allowed. Supplied source-mask controls qualify that API, not general production acquisition of dictionary/name masks. Literal, name, negation and repetition controls are retained in the fixed inputs.

The original Apple build took 114.70 seconds; its test body took 2.363 seconds. The original valid Android test body took 44.537 seconds. The corrected Apple build took 37.24 seconds, and the final Android test body took 34.698 seconds. Both final runs restored state. Apple used an isolated source/resource clone after the shared source was restored before root's archive retry. Android QA packages were removed and the owned emulator was stopped; the main package remained unchanged.

Apple's raw `mixed` field uses script/speech faces; Android's uses the default romanized display face. Exact selected spans and readings match. Explicit derived display views preserve this distinction. Agent reviews and their disagreements remain frozen; neither mechanical parity nor empty outputs imply semantic correctness.
