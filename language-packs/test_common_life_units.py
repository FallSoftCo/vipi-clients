import unittest
import authored_common_life_units as author


class CommonLifeUnitsTests(unittest.TestCase):
    def test_number_groups_preserve_swahili_people_and_objects(self):
        rows=list(author.records())
        def matching(source,target,left,right):
            return [r for r in rows if (r['source_language'],r['target_language'],r['source'],r['target'])==(source,target,left,right)]
        self.assertTrue(matching('en','sw','things','vitu'))
        self.assertTrue(matching('sw','en','mwanamke','woman'))
        self.assertFalse(matching('en','sw','things','kitu'))
        self.assertFalse(matching('sw','en','mwanamke','women'))
        self.assertTrue(all(r['usage']['whole_reference'] is False for r in rows))

    def test_context_sensitive_source_forms_and_japanese_readings_are_withheld(self):
        rows=list(author.records())
        for row in rows:
            self.assertFalse(row['source_language']=='en' and row['source'].lower() in {'man','men','word','words','service','services','challenge','challenges','minute','minutes'})
            self.assertFalse(row['source_language']=='ko' and row['source'] in {'날','날들','일','분'})
            self.assertFalse(row['source_language']=='fr' and row['source'].lower() in {'femme','femmes','homme','hommes','langue','langues'})
            self.assertFalse(row['source_language']=='it' and row['source'].lower() in {'paese','paesi','lingua','lingue'})
            self.assertFalse(row['target_language']=='ja' and row['target'] in {'日','分'})
            if row['target_language'] in {'ar','zh','ja','ko'}:self.assertTrue(row['reading'])
        self.assertTrue(any(r['source_language']=='sw' and r['source']=='neno' and r['target']=='word' for r in rows))

    def test_unique_records_and_complete_lexical_scope(self):
        rows=list(author.records())
        self.assertEqual(len(rows),len({r['logical_id'] for r in rows}))
        self.assertEqual(110,len({(r['source_language'],r['target_language']) for r in rows}))
        for row in rows:
            for side in ['source','target']:
                self.assertEqual([{'focus':row[side]}],row['usage'][side+'_frame_pattern'])
                self.assertEqual(row[side],row[side+'_context'])


if __name__=='__main__':unittest.main()
