import unittest
from authored_conversation import records
from authored_conversation_expansion import expanded_records
from mapping_catalog import validate


class ExpansionTests(unittest.TestCase):
    def test_disjoint_incremental_batch_retains_lexical_scope(self):
        prior={r['logical_id'] for r in records()};values=list(expanded_records())
        self.assertEqual(len(values),1800)
        self.assertFalse(prior & {r['logical_id'] for r in values})
        self.assertEqual(len({(r['source_language'],r['target_language']) for r in values}),90)
        for row in values:
            validate(row)
            a,b=row['source_span'];x,y=row['target_span']
            self.assertEqual(row['source_context'][a:b],row['source'])
            self.assertEqual(row['target_context'][x:y],row['target'])
            if row['target_language'] in ('ar','zh','ja','ko'):self.assertTrue(row['reading'])
        friend=next(r for r in values if r['source_language']=='ar' and r['target_language']=='en' and 'friend_person' in r['logical_id'])
        a,b=friend['source_span']
        self.assertEqual(friend['source'],'صديق')
        self.assertEqual(friend['source_context'][b],'ي')


if __name__=='__main__':unittest.main()
