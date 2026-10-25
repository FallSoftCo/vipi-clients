#!/usr/bin/env python3
"""Download a pinned, bounded research artifact; not a mobile release model."""
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
ROOT = 'https://huggingface.co/intfloat/multilingual-e5-small/'
FILES = {
    'onnx/model_qint8_avx512_vnni.onnx': (118346824, 'dd476dd0c2514e9b9be83aeb3853fac0763e0bdf4a71645407587d77c48a2d88'),
    'onnx/tokenizer.json': (17082730, '0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39'),
    'onnx/config.json': (653, None),
    'onnx/tokenizer_config.json': (443, None),
    'onnx/special_tokens_map.json': (167, None),
    'README.md': (2_097_152, None),
}


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'model': 'intfloat/multilingual-e5-small', 'revision': REVISION,
               'license': 'MIT (upstream model card)', 'mobile_qualified': False, 'files': []}
    for name, (bound, expected) in FILES.items():
        url = ROOT + 'resolve/' + REVISION + '/' + name
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + '.partial')
        digest = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(url, timeout=120) as response, partial.open('xb') as dest:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > bound:
                    raise ValueError('Download exceeds pinned bound: ' + name)
                digest.update(chunk)
                dest.write(chunk)
        if (expected and digest.hexdigest() != expected) or (name != 'README.md' and size != bound):
            raise ValueError('Pinned artifact mismatch: ' + name)
        partial.rename(path)
        receipt['files'].append({'file': name, 'bytes': size, 'sha256': digest.hexdigest(), 'url': url})
        print(json.dumps(receipt['files'][-1]), flush=True)
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main(Path(sys.argv[1]))
