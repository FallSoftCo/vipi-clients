"""Data-contract checks complement actual native reader regressions."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class MarkedChineseDataTests(unittest.TestCase):
    def test_marked_resource_has_exact_declared_identity(self):
        raw = (ROOT / 'data/readings/chinese-ordinary.json').read_bytes()
        provenance = json.loads((ROOT / 'data/readings/chinese-ordinary.provenance.json').read_text())
        self.assertEqual(provenance['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(provenance['bytes'], len(raw))
        table = json.loads(raw)
        self.assertEqual(table['schema'], 'vipi-pinyin-pro-marked-2')
        characters = dict(table['characters'])
        self.assertEqual(characters['女'][0], 'nǚ')
        self.assertEqual(characters['绿'][0], 'lǜ')
        self.assertEqual(characters['牛'][0], 'niú')
        phrases = {x['source']: x['readings'] for x in table['patterns']}
        for original, traditional, readings in [('音乐','音樂',['yīn','yuè']),
                ('银行','銀行',['yín','háng']),('重庆','重慶',['chóng','qìng']),
                ('妈妈','媽媽',['mā','ma'])]:
            self.assertEqual(phrases[original], readings)
            self.assertEqual(phrases[traditional], readings)
        self.assertEqual(phrases['什麼'], ['shén','me'])
        self.assertEqual(phrases['孩子'], ['hái','zi'])

    def test_first_install_preview_contains_authored_tones(self):
        zh = json.loads((ROOT / 'data/examples/immersion-preview.json').read_text())['languages']['zh']
        self.assertEqual([zh['words'][x]['reading'] for x in ['coffee','tomorrow','river']],
                         ['kāfēi','míngtiān','hé'])
        self.assertEqual(zh['reading'], 'Míngtiān yīqǐ hē kāfēi ma? Wǒ zhīdào hébiān yǒu ge xiǎo dìfang.')
        # The audio input remains written Chinese, independently from its guide.
        self.assertEqual(zh['text'], '明天一起喝咖啡吗？我知道河边有个小地方。')

if __name__ == '__main__': unittest.main()
