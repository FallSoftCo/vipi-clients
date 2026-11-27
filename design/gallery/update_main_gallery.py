"""Apply Vipi cards to the existing published collection with its native renderer."""
import ast
import fcntl
import hashlib
import html
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from datetime import datetime, timezone
from types import SimpleNamespace

root = Path('/home/ai/Development/8bar-houdini/showcase')
out = root.parent / 'output'
base = 'vipi-studio-20261120'
sys.path.insert(0, str(root))
from activity import order_catalog
from catalog_transport import packed_catalog, packed_cards, bootstrap_markup, preview_catalog

def read_json(path):
    return json.loads(path.read_bytes())

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def validated_asset(url):
    path = urlsplit(url)
    parts = Path(path.path).parts
    if path.netloc or path.scheme or not parts or parts[0] != base or '..' in parts:
        raise ValueError(url)
    if not (out / path.path).is_file():
        raise FileNotFoundError(url)

def renderer():
    source = (root / 'build.py').read_text()
    tree = ast.parse(source)
    start = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.FunctionDef) and n.name == 'file_size')
    end = next(i for i,n in enumerate(tree.body) if ast.get_source_segment(source,n) == 'asset_stats.publish_outputs()')
    return compile(ast.Module(body=tree.body[start:end],type_ignores=[]), str(root / 'build.py'), 'exec')

def publish():
    source = (out / 'catalog-extras' / (base + '.json'))
    new_cards = read_json(source)
    old = read_json(out / 'showcase-catalog.json')
    activity_path = out / 'showcase-activity.json'
    history = read_json(activity_path)
    new_ids = {c['id'] for c in new_cards}
    assert len(new_ids)==len(new_cards) and new_ids
    # Other publishers also use the Vipi Studio ID prefix. Preserve their
    # cards without requiring them in this shelf's source catalog.
    old_vipi = {
        c['id']: c
        for c in old
        if c['id'].startswith('vipi-studio-')
        and urlsplit(c.get('poster') or '').path.startswith(f'{base}/')
    }
    assert set(old_vipi) <= new_ids, 'Removal requires a separate change'
    old_markup = (out / 'showcase-static.html').read_text()
    new_urls = set()
    for c in new_cards:
        assert c['id'].startswith('vipi-studio-') and c['brand']=='Vipi' and c['privateQaOnly']
        new_urls.update([c['poster'], c['interactivePreview'], *(d['path'] for d in c['downloads'])])
    for url in new_urls:
        validated_asset(url)
    def asset(url):
        if url not in new_urls and html.escape(url,quote=True) not in old_markup:
            raise ValueError('Outside existing published links: ' + url)
        return url
    # Use each artwork's source timestamp. Updating the common review page
    # must not mark older unaffected cards as freshly produced.
    fresh = []
    for c in new_cards:
        when = datetime.fromisoformat(c['updatedAt']).timestamp()
        previous = history['entries'].get(c['id'])
        entries = {'version':2, 'entries':{c['id']:previous}} if previous else {}
        result, delta = order_catalog([c], out, entries, now=when)
        history['entries'][c['id']] = delta['entries'][c['id']]
        fresh.extend(result)
    others = [c for c in old if c['id'] not in new_ids]
    catalog = sorted(others + fresh, key=lambda c:c['updatedAt'],reverse=True)
    assert [c for c in catalog if c['id'] not in new_ids] == others
    if catalog == old:
        print('Verified. The existing gallery already includes these Vipi cards.')
        return
    for name in ['farm.js','frames.js','showcase.js','showcase.css']:
        assert digest(root/name)==digest(out/name), 'Shared theme update pending'
    previous_revision = (out / 'showcase-revision.txt').read_text().strip()
    existing_ids={c['id'] for c in old}
    assert len(existing_ids)==len(old) and len(catalog)==len(others)+len(new_ids)
    with tempfile.TemporaryDirectory(dir=out,prefix='.vipi-publish-') as tmp:
        stage = Path(tmp)
        def write(path, content):
            assert path.parent==out
            (stage / path.name).write_text(content)
        env = dict(catalog=catalog,history=history,activity_path=activity_path, ROOT=root, OUT=out,
                   e=html.escape, hashlib=hashlib, json=json, urlsplit=urlsplit, parse_qs=parse_qs,
                   packed_catalog=packed_catalog,packed_cards=packed_cards,bootstrap_markup=bootstrap_markup,
                   preview_catalog=preview_catalog,asset=asset,atomic_write=write,asset_stats=SimpleNamespace(atomic_transfer=True))
        exec(renderer(),env)
        for c in fresh:
            assert ('id="'+c['id']+'"') in env['static_result']
        assert read_json(stage/'showcase-catalog.json') == catalog
        assert (out/'showcase-revision.txt').read_text().strip() == previous_revision
        for name in ['showcase-catalog.json','showcase-previews.json','showcase-cards.html','showcase-static.html','index.html','showcase-activity.json','showcase-revision.txt']:
            (stage/name).chmod(0o644)
            os.replace(stage/name,out/name)
        print(json.dumps(dict(previousRevision=previous_revision, revision=env['revision'], preservedCards=len(others), publishedVipiCards=len(fresh))))
if __name__=='__main__':
    with (out/'.showcase-build.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        publish()
