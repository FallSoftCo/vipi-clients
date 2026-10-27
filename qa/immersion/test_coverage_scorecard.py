#!/usr/bin/env python3
"""Check that depth accounting cannot inflate sparse or partial immersion."""
import unittest
from coverage_scorecard import depth, summarize, require_coverage_population
from analyze_lexical_qualification import identity

def row(name, text, tokens, spans, intact=True):
    case=dict(id=name,dataset="sms",source="en",target="es",original=text)
    outcome=dict(id=name,dataset="sms",source="en",target="es",source_token_ranges=tokens,
                 combined_spans=[dict(start=a,end=b) for a,b in spans],
                 identifier_guard=intact,baseline_retained=True)
    return case,outcome

class CoverageAccounting(unittest.TestCase):
    def test_carrier_after_surrogate_pair_is_not_whole_word(self):
        case,value=row("partial","🙂 weddings!",[[3,11]],[(3,10)])
        measured=depth(case,value)
        self.assertEqual((measured["tokens"],measured["touched"],measured["fully_covered"]),(1,1,0))
        value["combined_spans"].append(dict(start=10,end=11))
        self.assertEqual(depth(case,value)["fully_covered"],1)

    def test_empty_and_identifier_failures_stay_in_denominator(self):
        pairs=[row("ok","hello",[[0,5]],[(0,5)]),
               row("none","bye",[[0,3]],[],False),
               row("emoji","🙂",[],[])]
        cases={identity(c):c for c,_ in pairs}
        result=summarize([r for _,r in pairs],cases)
        self.assertEqual(result["messages"],3)
        self.assertEqual(result["messages_with_span"],1)
        self.assertEqual(result["availability_percent"],33.333)
        self.assertEqual(result["depth"]["messages_at_depth"]["25"]["touched_percent"],33.333)
        self.assertEqual(result["depth"]["messages_without_native_words"],1)
        self.assertFalse(result["availability_floor_met"])
        self.assertIsNone(result["semantic_accuracy"])

    def test_missing_data_and_legacy_depth_cannot_pass(self):
        self.assertEqual(summarize([],{}),dict(status="unmeasured",messages=0))
        case,value=row("old","hello",[[0,5]],[(0,5)])
        del value["source_token_ranges"]
        result=summarize([value],{identity(case):case})
        self.assertIsNone(result["depth"])
        self.assertFalse(result["independent_semantic_acceptance"])

    def test_native_alphabetic_classification_is_preserved(self):
        case,value=row("mark","\u064e",[[0,1]],[])
        self.assertEqual(depth(case,value)["tokens"],1)

    def test_targeted_regressions_are_not_a_coverage_population(self):
        with self.assertRaises(ValueError):
            require_coverage_population(dict(evaluation_scope="targeted-regression-only"))

    def test_bad_utf16_boundary_and_overlapping_spans_fail(self):
        case,value=row("bad","🙂 hello",[[1,2]],[])
        with self.assertRaises((AssertionError,UnicodeDecodeError)):
            depth(case,value)
        case,value=row("overlap","hello",[[0,5]],[(0,4),(3,5)])
        with self.assertRaises(AssertionError):
            depth(case,value)

if __name__=="__main__":
    unittest.main()

