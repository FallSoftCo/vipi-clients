import copy
import unittest
from import_massive import slots, usable, partition

class MassiveBoundaries(unittest.TestCase):
    def source(self):
        return dict(locale="en-US",utt="wake me on friday",annot_utt="wake me on [date : friday]",
            scenario="alarm",intent="alarm_set")
    def target(self):
        return dict(locale="ja-JP",utt="金曜日に起こして",annot_utt="[date : 金曜日] に起こして",
            scenario="alarm",intent="alarm_set",slot_method=[dict(slot="date",method="translation")],
            judgments=[dict(intent_score=1,slots_score=1,grammar_score=4,spelling_score=2,
                language_identification="target") for _ in range(3)])
    def test_original_translation_and_annotation_spacing(self):
        self.assertIsNone(usable(self.target(),self.source()))
    def test_localization_is_not_translation(self):
        row=self.target();row["slot_method"][0]["method"]="localization"
        self.assertEqual(usable(row,self.source()),"localized_or_unknown_slot_method")
    def test_omitted_entity_is_rejected(self):
        row=self.target();row["annot_utt"]="金曜日に起こして"
        self.assertEqual(usable(row,self.source()),"invalid_or_changed_slots")
    def test_malformed_annotation_is_rejected(self):
        row=self.target();row["annot_utt"]="[date : 木曜日] に起こして"
        self.assertEqual(usable(row,self.source()),"invalid_or_changed_slots")
    def test_disagreement_is_not_overruled_by_majority(self):
        row=self.target();row["judgments"][0]["intent_score"]=0
        self.assertEqual(usable(row,self.source()),"source_judgment_disagreement")
    def test_split_and_prior_source_leakage(self):
        self.assertEqual(partition({"train"},False,False),"development")
        self.assertEqual(partition({"train","dev"},False,False),"reserved")
        self.assertEqual(partition({"train","test"},False,False),"reserved")
        self.assertEqual(partition({"train"},True,False),"excluded-existing-source")
        self.assertEqual(partition({"test"},False,True),"excluded-inspected")

if __name__=="__main__": unittest.main()
