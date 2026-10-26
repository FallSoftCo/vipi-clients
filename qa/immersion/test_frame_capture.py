import copy
import json
from pathlib import Path
import tempfile
import unittest
from evaluate_frame_capture import evaluate,sha,surface


class FrameCaptureTests(unittest.TestCase):
    def test_actual_capture_and_unicode_scope_are_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);capture=root/'capture.json';build=root/'build.json';report=root/'report.json'
            actual={'case':'book','source':'en','target':'es','original':'🙂 book','translation':'🙂 libro','status':'executed','start':3,'end':7}
            capture.write_text(json.dumps({'complete':True,'cases_expected':1,'cases_completed':1,'results':[actual]}))
            build.write_text(json.dumps({'pairs':[{'pack_id':'en-es'}]}))
            row=dict(actual,mapping_count=1,lookup_alignment_ms=2,spans=[{'start':3,'end':7,'targetStart':3,'targetEnd':8,'original':'book','translated':'libro','reading':None}])
            value={'schema':'vipi-frame-capture-1','platform':'Android','cases':1,'translation_capture_sha256':sha(capture),'build_sha256':sha(build),'results':[row]}
            report.write_text(json.dumps(value));self.assertEqual(evaluate(report,capture,build)['cases_with_immersion'],1)
            bad=copy.deepcopy(value);bad['results'][0]['translation']='different';report.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):evaluate(report,capture,build)
            report.write_text(json.dumps(value));build.write_text('{}')
            with self.assertRaises(ValueError):evaluate(report,capture,build)
        with self.assertRaises(ValueError):surface('🙂',0,1)
        self.assertEqual(surface('كتابًا',0,4),'كتاب')


if __name__=='__main__':unittest.main()
