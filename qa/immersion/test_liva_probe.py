import unittest
from prepare_liva_swahili_probe import parse_transcript, select


class LivaProbeTests(unittest.TestCase):
    def test_preserves_utterance_and_separates_metadata(self):
        row = list(parse_transcript('Speaker 2 [00:00:01.100 - 00:00:02.000]: Habari, rafiki!  \n\n'))[0]
        self.assertEqual(row['text'], 'Habari, rafiki!  ')
        self.assertEqual(row['speaker'], 'Speaker 2')
        self.assertEqual(row['start'], '00:00:01.100')

    def test_unknown_structure_and_bad_intervals_fail(self):
        for text in ['Unlabelled text', 'Speaker 1 [00:00:02.000 - 00:00:01.000]: Habari',
                     'Speaker 1 [00:66:01.000 - 00:66:02.000]: Habari']:
            with self.assertRaises(ValueError): list(parse_transcript(text))

    def test_selection_is_order_independent_deduplicated_and_bounded(self):
        turn = lambda text: 'Speaker 1 [00:00:01.000 - 00:00:02.000]: '+text+'\n'
        rows = [{'file_name':'b.wav','transcript':turn('Habari!')+turn('Karibu!')},
                {'file_name':'a.wav','transcript':turn('Habari!')+turn('[laughter]')+turn('Tutaonana.')}]
        selected, counts = select(rows, 1)
        self.assertEqual(select(list(reversed(rows)), 1), (selected, counts))
        self.assertEqual(len(selected), 2)
        self.assertEqual(counts['exact_normalized_duplicates'], 1)
        self.assertEqual(counts['nonlexical_turns'], 1)


if __name__ == '__main__': unittest.main()
