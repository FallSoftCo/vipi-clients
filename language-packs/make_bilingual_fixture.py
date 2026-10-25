"""Synthetic signed schema-3 native QA, including conflicting/missing readings."""
import argparse
import base64
import json
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from export_bilingual import export_pair
from test_bilingual import fixture_catalog


def main(output):
    if output.exists():
        raise ValueError('Use a fresh fixture output')
    key = ec.generate_private_key(ec.SECP256R1())
    cases = []
    samples = [
        ('en', 'zh', 'Want coffee?', '明天喝咖啡。', 'coffee', '咖啡', 'kāfēi'),
        ('en', 'ja', 'Want coffee?', 'コーヒーはいかが？', 'coffee', 'コーヒー', 'kōhī'),
        ('en', 'ko', 'Want coffee?', '커피 마실래?', 'coffee', '커피', 'keopi'),
        ('en', 'ar', 'Want coffee?', 'هل تريد قهوة؟', 'coffee', 'قهوة', 'qahwa'),
        ('ar', 'en', 'قَـهْوَة', 'coffee', 'قَـهْوَة', 'coffee', None),
        ('en', 'fr', 'A bank near the river.', 'Une rive près du fleuve.', 'bank', 'rive', None),
    ]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        catalog = root / 'catalog.sqlite'
        fixture_catalog(catalog)
        for source, target, text, translation, expected, written, reading in samples:
            pack = root / (source + '-' + target)
            export_pair(catalog, source, target, pack, 1, key, 'synthetic-bilingual-qa')
            cases.append(dict(id=source+'-'+target, source=source, target=target, text=text, translation=translation,
                              expected=expected, written=written, reading=reading,
                              **{name:base64.b64encode((pack/file).read_bytes()).decode()
                                 for name,file in [('manifest','manifest.json'),('signature','manifest.sig'),('database','vocabulary.sqlite')]}))
    public = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    output.write_text(json.dumps({'purpose':'SYNTHETIC BILINGUAL QA ONLY', 'public_key':base64.b64encode(public).decode(), 'cases':cases}, ensure_ascii=False)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    main(parser.parse_args().output)
