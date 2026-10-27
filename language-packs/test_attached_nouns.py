import unittest
from authored_attached_nouns import korean_suffixes,meaning_for,records
from context_patterns import frame_parts,side_is_unit
from export_reviewed_frames import variants


def unit(source,target,left,right,topic,reading=''):
    return dict(source_language=source,target_language=target,source=left,target=right,
        meaning=meaning_for(topic),reading=reading,id='retained-test-unit',record_sha256='a'*64)


class AttachedNounTests(unittest.TestCase):
    def test_finite_particle_allomorphs_and_no_runtime_stemming(self):
        self.assertEqual(korean_suffixes('책')[:4],['은','이','을','과'])
        self.assertEqual(korean_suffixes('학교')[:4],['는','가','를','와'])
        self.assertNotIn('를',korean_suffixes('책'))
        with self.assertRaises(ValueError):korean_suffixes('not Hangul')

    def test_attached_forms_preserve_both_focuses_and_exact_reading(self):
        rows=list(records([unit('ko','sw','학교','shule','school_place')]))
        self.assertEqual(len(rows),3)
        for row in rows:
            self.assertFalse(row['usage']['whole_reference'])
            self.assertFalse(row['usage']['lexical_unit'])
            for side in ('source','target'):
                pattern=frame_parts(row,side)
                values=variants(pattern,side_is_unit(row['usage'],side))
                self.assertIn(row[side+'_context'],values)
                start,end=row[side+'_span'];self.assertEqual(row[side+'_context'][start:end],row[side])
        row,=records([unit('sw','ja','shule','学校','school_place','gakkō')])
        self.assertEqual(row['source_context'],'shuleni')
        self.assertEqual(row['reading'],'gakkō')
        self.assertTrue(row['usage']['target_lexical_unit'])
        self.assertFalse(row['usage']['source_lexical_unit'])

    def test_unassessed_house_home_and_unrelated_senses_do_not_gain_scope(self):
        self.assertEqual(list(records([unit('sw','en','nyumba','house','house_building')])),[])
        wrong=unit('ko','en','문','sentence','door_physical');wrong['meaning']='written sentence, not a physical door'
        self.assertEqual(list(records([wrong])),[])
        self.assertEqual(list(records([unit('en','es','book','libro','reading_book')])),[])


if __name__=='__main__':unittest.main()
