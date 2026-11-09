The November 9 review shows that source noun tagging and a longer matching string
do not, by themselves, establish the intended translation. A useful next question
is whether the retained parallel occurrences contain evidence for choosing among
target alternatives. This is a research direction, not an accepted runtime change.

Apertium treats lexical selection as choosing a target translation among
alternatives with the same source part of speech. It explicitly distinguishes
that task from separating every fine-grained dictionary sense: several senses
may legitimately share one target word. That distinction matters for Vipi's
correct `circle→círculo` and `nature→naturaleza` outputs, whose selected corpus
witnesses have different senses from the chat. An all-senses-agree veto would
discard some useful mappings. [Official lexical-selection description](https://wiki.apertium.org/wiki/Lexical_selection).

The project's parallel-corpus recipe derives candidate translations from
aligned bilingual occurrences, then estimates context rules. Its maximum
likelihood method compares a contextual alternative's frequency with a default;
its maximum entropy method assigns weights to contextual n-grams. These are
estimation procedures, not correctness guarantees. Vipi must retain competing
choices, independent occurrence/component counts and the actual aligned spans
before assessing whether its existing data can support such a selector.
[Official training recipe](https://wiki.apertium.org/wiki/Learning_rules_from_parallel_and_non-parallel_corpora).

The existing `apertium-lex-tools` module compiles lexical rules, including
contextual select/remove operations and weighted competition. This establishes
an available implementation technique; the previous full Apertium transfer
probe did not qualify its language pair as Vipi's meaning authority. Native
client integration, runtime cost and additional dependencies are undecided.
[Official module contract](https://wiki.apertium.org/wiki/Constraint-based_lexical_selection_module),
[upstream implementation](https://github.com/apertium/apertium-lex-tools).

The next evidence inventory must separate three failures: a missing suitable
target, an available target selected in the wrong context, and a protected
name/construction being split. A lexical selector cannot fix absent evidence or
establish name safety. The exposed season/title failures are development
diagnostics; any subsequent selection comparison needs frozen evaluation cases
and complete-output review. Do not fit a rule to those two messages and report
them as new accuracy evidence.
