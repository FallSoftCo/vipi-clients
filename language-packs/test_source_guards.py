import json
import sqlite3
import unittest
from build_source_guards import SCHEMA,collect,finish


class SourceGuardsTests(unittest.TestCase):
    def test_native_compound_and_omitted_meanings_survive_without_translations(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript(SCHEMA)
            collect(db,{'lang_code':'zh','word':'板藍根','pos':'noun','senses':[{'glosses':['herb root']}],
                        'forms':[{'form':'板蓝根','tags':['Simplified-Chinese']}]},1)
            for pos,gloss in [('noun','full moon'),('verb','to turn one month old')]:
                collect(db,{'lang_code':'zh','word':'滿月','pos':pos,'senses':[{'glosses':[gloss]}],
                            'forms':[{'form':'满月','tags':['Simplified-Chinese']}]},2)
            collect(db,{'lang_code':'zh','word':'他','pos':'pron','senses':[{'glosses':['he']}]},3)
            collect(db,{'lang_code':'ja','word':'月光','pos':'noun','senses':[{'glosses':['moonlight']}]},4)
            collect(db,{'lang_code':'zh','word':'月光','pos':'noun','senses':[{'glosses':['moonlight']}],
                        'forms':[{'form':'错误','tags':['romanization']}]},5)
            finish(db)
            rows={w:(inner,ambiguous,json.loads(evidence)) for w,inner,ambiguous,evidence in db.execute('SELECT * FROM source_guards')}
            self.assertEqual(rows['板蓝根'][:2],(1,0));self.assertEqual(rows['满月'][:2],(1,1))
            self.assertEqual(len(rows['满月'][2]),2)
            self.assertNotIn('他',rows);self.assertNotIn('错误',rows)
            self.assertEqual(len(rows['月光'][2]),1)
