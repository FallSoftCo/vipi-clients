import unittest
from swahili_carriers import records, transitivity

class SuppliedSwahiliCarriers(unittest.TestCase):
    def forms(self):
        return [
            ("kukopesha", ["infinitive"]),
            ("ninakopesha", ["first-person", "present", "singular"]),
            ("tulikopesha", ["first-person", "past", "plural"]),
            ("-nikopesha", ["first-person", "indicative", "object-concord", "singular"]),
            ("-mkopesha", ["class-1", "indicative", "object-concord", "singular"]),
            ("-jikopesha", ["indicative", "object-concord", "reflexive"]),
            ("kopesh a", ["present"]),
            ("-yekopesha", ["relative", "object-concord"]),
        ]
    def test_supplied_components_preserve_entire_lexical_root_and_native_affixes(self):
        rows = list(records("kopesha", "verb", [], self.forms(), ["fixture-defined-causative"]))
        by_form = {record[0]: (record, evidence) for record, evidence in rows}
        self.assertEqual(set(by_form), {"kunikopesha", "kumkopesha", "ninanikopesha", "ninamkopesha", "tulinikopesha", "tulimkopesha"})
        for written, (record, evidence) in by_form.items():
            self.assertEqual(written[record[1]:record[2]], "kopesha")
            self.assertIn(evidence["supplied_base"], {"kukopesha", "ninakopesha", "tulikopesha"})
            self.assertNotIn("ji", evidence["supplied_object"][1:-len("kopesha")])
    def test_no_unattested_object_or_base_and_no_irregular_generalization(self):
        self.assertEqual(list(records("kopesha", "verb", [], self.forms()[:3], ["fixture-defined-causative"])), [])
        self.assertEqual(list(records("kopesha", "verb", [], self.forms()[3:], ["fixture-defined-causative"])), [])
        for head in ["ona", "enda", "la", "ja", "Kopesha", "kopesha pesa"]:
            self.assertEqual(list(records(head, "verb", [], self.forms(), ["fixture-defined-causative"])), [])
        self.assertEqual(list(records("kopesha", "noun", [], self.forms(), ["fixture-defined-causative"])), [])
    def test_object_tables_alone_do_not_establish_transitivity(self):
        import json
        def row(gloss, tags, references=[]):
            return (json.dumps([gloss]), json.dumps(tags), json.dumps(references), "[]")
        self.assertEqual(transitivity([row("to faint", [])]), [])
        self.assertEqual(list(records("kopesha", "verb", [], self.forms(), [])), [])
        self.assertTrue(transitivity([row("to lend", ["transitive"])]))
        self.assertFalse(transitivity([row("to lend", ["transitive", "obsolete"])]))
        self.assertTrue(transitivity([row("Causative form of -kopa: to lend",
            ["causative", "form-of"], [dict(word="-kopa", extra="to lend")])]))
    def test_final_vowel_reflexive_and_relative_forms_are_not_composed(self):
        forms = self.forms()[:3] + [
            ("-nikopeshe", ["object-concord", "indicative"]),
            ("-jikopesha", ["object-concord", "indicative", "reflexive"]),
            ("-yekopesha", ["object-concord", "relative"])]
        self.assertEqual(list(records("kopesha", "verb", [], forms, ["fixture-defined-causative"])), [])

if __name__ == "__main__": unittest.main()
