"""Independent read-only reconstruction; imports no exporter code."""
from pathlib import Path
import sqlite3, json, hashlib, zlib, resource, signal, os, time, collections

ROOT = Path('/srv/fallsoft/staging/vipi-native-baseline-catalog-20261109-r01')
OUT = ROOT / 'root-independent-audit-r01'
OUT.mkdir(exist_ok=False)
resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
os.nice(10)
signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('independent audit 120s')))
signal.alarm(120)
started = time.monotonic()
receipt = {'success': False, 'scope': 'Read-only independent comparison of exported catalog to all retained original candidate/proof relationships'}

def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def read_database(path):
    path = Path(path)
    assert path.is_file() and not any(Path(str(path) + s).exists() for s in ['-wal', '-shm', '-journal'])
    db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
    db.execute('PRAGMA query_only=ON')
    db.execute('PRAGMA cache_size=-8192')
    return db

try:
    assert sha(ROOT / 'protocol-r02.json') == 'bbb40ba3c6dab94722490d6a579de4219d442956f7290b7dce047dd54bfac612'
    assert sha(ROOT / 'export-r02/manifest.json') == '9c0d7af245a599bfaadc07dc6fb84c41a3bf72b5e657adcee0b7b68efa96a281'
    assert sha(ROOT / 'export-r02/proof-manifest.json') == '0e1a45b50e3dc6a4c49c7da3751641a817d39db87410ac266b3fef62d220b32d'
    protocol = json.loads((ROOT / 'protocol-r02.json').read_text())
    manifest = json.loads((ROOT / 'export-r02/manifest.json').read_text())
    parent = json.loads((ROOT / 'census/receipt.json').read_text())
    assert sha(ROOT / 'census/receipt.json') == protocol['parent_census_sha256']
    assert manifest['dependencies'] == protocol['inputs']
    for name, item in protocol['inputs'].items():
        assert sha(item['path']) == item['sha256'], name
    path = ROOT / 'export-r02/catalog.sqlite'
    assert path.stat().st_size == manifest['database_bytes'] == 127016960
    assert sha(path) == manifest['database_sha256'] == '8b8198a65480a67149fc174bbc03d4eb4644ead7cb5f5aea48e050820122c9a8'
    db = read_database(path)
    catalog = read_database(protocol['inputs']['catalog']['path'])
    heads = read_database(protocol['inputs']['heads']['path'])
    context = read_database(protocol['inputs']['context_pack']['path'])
    lookup = json.loads(Path(protocol['inputs']['lookup']['path']).read_text())
    frequency = json.loads(Path(protocol['inputs']['fixed_keys']['path']).read_text())
    frequency_rows = sorted(frequency['unigram_keys'] + frequency['multiword_keys'],
                            key=lambda row: (-row['source_message_frequency'], -row['occurrence_frequency'], row['source_key']))
    ranks = {row['source_key']: index for index, row in enumerate(frequency_rows)}
    assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    ordinary_ids = {row[0] for row in heads.execute('SELECT id FROM heads')}
    exported_ordinary = {row[0] for row in db.execute('SELECT id FROM candidates WHERE baseline=1')}
    assert ordinary_ids == exported_ordinary, 'Entire original ordinary ID set must survive'
    original = {row[0]: row for row in catalog.execute('SELECT id,source_key,baseline,experimental,record,audit FROM heads WHERE baseline=1 OR experimental=1')}
    assert {row[0] for row in db.execute('SELECT id FROM candidates')} == set(original)
    groups = collections.defaultdict(list)
    conditional_ids = set()
    for row in db.execute('SELECT * FROM candidates ORDER BY id'):
        ident, key, context_id, baseline, conditional, rank, raw, audit_raw, raw_sha, audit_sha = row
        old = original[ident]
        assert (key, baseline, raw, audit_raw) == (old[1], old[2], old[4], old[5])
        assert conditional == int(not baseline) and old[3] == 1
        assert rank == ranks.get(key, 10**9)
        assert hashlib.sha256(raw.encode()).hexdigest() == raw_sha
        assert hashlib.sha256(audit_raw.encode()).hexdigest() == audit_sha
        record, audit = json.loads(raw), json.loads(audit_raw)
        assert context_id == record['context_id'] and record['id'] == ident and record['source_key'] == key
        if baseline:
            assert heads.execute('SELECT record FROM heads WHERE id=?', (ident,)).fetchone() == (raw,)
        else:
            conditional_ids.add(ident)
            assert lookup['original_head_records'][ident] == record
            actual_links = {tuple(link[field] for field in ['source_form_id', 'target_form_id', 'source_term_id', 'target_term_id']) for link in audit['override_links']}
            assert actual_links == {tuple(link) for link in lookup['original_override_links'][ident]}
        groups[context_id].append((ident, record, audit))
    expected_keys = {(ident, key) for ident, keys in lookup['head_keys'].items() for key in keys}
    assert set(db.execute('SELECT head_id,source_key FROM head_keys')) == expected_keys
    assert set(lookup['head_keys']) <= conditional_ids
    for table in ['known_families', 'source_roles', 'function_words']:
        assert db.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall() == context.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall()
    proofs = json.loads((ROOT / 'export-r02/proof-manifest.json').read_text())
    assert set(proofs) == set(groups)
    seen_evidence = set()
    edges = 0
    policy_fields = ['source_unit_id', 'target_unit_id', 'source_tokens', 'target_tokens', 'source_utf16', 'target_utf16', 'mutual_anchor', 'crossing_union_edges', 'source_mask_ids', 'target_mask_ids', 'reasons', 'structural_eligible']
    for context_id, records in groups.items():
        blob = heads.execute('SELECT proof FROM contexts WHERE id=?', (context_id,)).fetchone()[0]
        blob_sha = hashlib.sha256(blob).hexdigest()
        assert proofs[context_id] == {'blob_sha256': blob_sha, 'selected_heads': sorted(row[0] for row in records)}
        proof_heads = {row['head_id']: row for row in json.loads(zlib.decompress(blob))['result']['heads']}
        for ident, record, audit in records:
            proof = proof_heads[record['head_id']]
            assert audit['original_proof_blob_sha256'] == blob_sha
            assert proof['head_id'] == audit['head_id'] and proof['source_unit_id'] == audit['source_unit_id']
            assert proof['target_text'] == record['target_face']
            if ident in ordinary_ids:
                assert record['head_readings'] == proof['readings']
                assert record['head_shared_senses'] == [link for link in proof['shared_senses'] if link['structural_eligible']]
            expected = {}
            def require_object(kind, identity, value):
                raw = encode(value).decode()
                evidence_id = hashlib.sha256(encode([kind, value])).hexdigest()
                expected[(kind, identity, evidence_id)] = (kind, raw)
            for side in ['source', 'target']:
                for form in proof[side + '_forms']:
                    require_object(side + '_form', form['form_id'], {k: v for k, v in form.items() if k != 'terms'})
                    for term in form['terms']:
                        require_object(side + '_term', form['form_id'] + ':' + term['term_id'], term)
            for link in proof['shared_senses']:
                require_object('shared_link', hashlib.sha256(encode(link)).hexdigest(), link)
            require_object('head_policy', proof['head_id'], {field: proof[field] for field in policy_fields})
            actual = {(kind, identity, evidence_id): (evidence_kind, value)
                      for kind, identity, evidence_id, evidence_kind, value in db.execute(
                          'SELECT h.kind,h.identity,h.evidence_id,e.kind,e.value_json FROM head_evidence h JOIN evidence e ON e.id=h.evidence_id WHERE h.head_id=?', (ident,))}
            assert actual == expected, ('original proof evidence differs', ident)
            edges += len(actual)
            seen_evidence.update(key[2] for key in actual)
    assert seen_evidence == {row[0] for row in db.execute('SELECT id FROM evidence')}
    assert edges == db.execute('SELECT count(*) FROM head_evidence').fetchone()[0]
    order = {'metadata': 'key', 'candidates': 'id', 'head_keys': 'head_id,source_key',
             'evidence': 'id', 'head_evidence': 'head_id,kind,identity,evidence_id',
             'known_families': 'source', 'source_roles': 'source', 'function_words': 'source'}
    total = hashlib.sha256(); total.update(b'{')
    logical_bytes = {}; actual_counts = {}; table_hashes = {}
    for index, table in enumerate(sorted(order)):
        if index: total.update(b',')
        total.update(encode(table) + b':[')
        digest = hashlib.sha256(); digest.update(b'[')
        count = byte_count = 0
        for row in db.execute('SELECT * FROM ' + table + ' ORDER BY ' + order[table]):
            raw = encode(row)
            if count: digest.update(b','); total.update(b',')
            digest.update(raw); total.update(raw)
            byte_count += len(raw); count += 1
            assert len(raw) <= 256 * 1024
        digest.update(b']'); total.update(b']')
        assert count == manifest['table_counts'][table]
        assert digest.hexdigest() == manifest['table_logical_sha256'][table]
        logical_bytes[table] = byte_count; actual_counts[table] = count; table_hashes[table] = digest.hexdigest()
    total.update(b'}')
    assert total.hexdigest() == parent['logical_rows_sha256']
    assert logical_bytes == parent['logical_UTF8_bytes']
    metadata = dict(db.execute('SELECT key,value FROM metadata'))
    assert metadata['kind'] == 'vipi.source-candidate-catalog' and metadata['permission'] == 'disabled_research_only'
    assert metadata['context_pack_sha256'] == protocol['inputs']['context_pack']['sha256']
    assert metadata['policy_sha256'] == protocol['contract_sha256'] == manifest['contract_sha256']
    assert metadata['source_manifest_sha256'] == hashlib.sha256(encode(protocol['inputs'])).hexdigest()
    for language in ['en', 'es']:
        dictionary = read_database(protocol['inputs']['dictionary_' + language]['path'])
        assert metadata['dictionary_' + language + '_sha256'] == protocol['inputs']['dictionary_' + language]['sha256']
        assert json.loads(metadata['dictionary_' + language + '_metadata_json']) == dict(dictionary.execute('SELECT key,value FROM metadata'))
        dictionary.close()
    receipt.update(success=True, ordinary_heads=len(ordinary_ids), conditional_heads=len(conditional_ids),
                   original_contexts=len(groups), conditional_heads_with_keys=len(lookup['head_keys']),
                   conditional_heads_without_keys=len(conditional_ids-set(lookup['head_keys'])),
                   exact_evidence_objects=len(seen_evidence), exact_relationships=edges,
                   table_counts=actual_counts, logical_UTF8_bytes=logical_bytes,
                   logical_rows_sha256=total.hexdigest(), manifest_sha256=sha(ROOT/'export-r02/manifest.json'),
                   database_sha256=sha(path), no_inference_or_activation=True,
                   all_ordinary_IDs_and_raw_records_preserved=True,
                   all_rejected_alternatives_and_original_readings_preserved=True)
except BaseException as exc:
    receipt['error'] = repr(exc)
    raise
finally:
    receipt['seconds'] = time.monotonic() - started
    receipt['script_sha256'] = sha(__file__)
    receipt['VmHWM_bytes'] = int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmHWM:'))) * 1024
    (OUT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
