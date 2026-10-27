import unittest
from authored_plural_units import records
from authored_everyday_units import MEANINGS


class PluralUnitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.rows=list(records({}))

    def test_swahili_plural_forms_do_not_borrow_singular_counterparts(self):
        for native,english in [('vitabu','books'),('marafiki','friends'),('mikutano','meetings'),('viwanja vya ndege','airports'),('miaka','years')]:
            targets={r['target'].casefold() for r in self.rows if r['source_language']=='sw' and r['source']==native and r['target_language']=='en'}
            self.assertEqual(targets,{english})

    def test_ambiguous_written_sources_require_a_separate_context_frame(self):
        for language,word in [('ar','كتب'),('ar','صور'),('ar','خطط'),('ar','أشهر'),('zh','问题'),('en','books'),('en','plans'),('en','trains')]:
            self.assertFalse(any(r['source_language']==language and r['source']==word for r in self.rows))
            self.assertTrue(any(r['target_language']==language and r['target']==word for r in self.rows))

    def test_existing_reading_is_reused_only_for_exact_form_and_meaning(self):
        baseline={('ja','本',MEANINGS['reading_book']):'hon',('ja','電話','a different meaning'):'invalid'}
        rows=list(records(baseline))
        self.assertTrue(all(r['reading']=='hon' for r in rows if r['target_language']=='ja' and r['target']=='本'))
        self.assertFalse(any(r['reading']=='invalid' for r in rows))
        self.assertTrue(all(r['usage']['whole_reference'] is False for r in rows))
        self.assertTrue(all(r['reading'] for r in rows if r['target_language'] in ('ar','zh','ja','ko')))
