import unittest
from prioritize_social_swahili import observed_windows, training_rows


class SocialSwahiliPriorityTests(unittest.TestCase):
    def test_excluded_material_cannot_supply_or_join_words(self):
        windows = set(observed_windows('Maji @rafiki safi https://example.com/nyumba pesa #habari leo 50sh kesho'))
        self.assertEqual(windows, {'maji', 'safi', 'pesa', 'leo', 'kesho'})
        self.assertIn('habari za leo', set(observed_windows('Habari za leo?')))

    def test_tsv_quotes_and_newlines_remain_inside_one_turn(self):
        self.assertEqual(list(training_rows('ID\ttweet\tlabel\n1\t"maji\nna chai"\tpositive\n')),
                         [('1', 'maji\nna chai')])

    def test_split_shape_and_duplicate_identifiers_fail(self):
        for text in ('tweet\tlabel\na\tb\n', 'ID\ttweet\tlabel\n1\ta\tb\n1\tc\td\n',
                     'ID\ttweet\tlabel\n1\ta\n'):
            with self.assertRaises(ValueError):
                list(training_rows(text))
