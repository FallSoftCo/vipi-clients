// Reproduce the QA data projection from the retained, hash-verified upstream package.
// This does not fetch/install dependencies or modify a native application.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';

if (process.argv.length !== 4) throw Error('Usage: node export-data.mjs PACKAGE_DIRECTORY OUTPUT_JSON');
const root = path.resolve(process.argv[2]);
const output = path.resolve(process.argv[3]);
const metadata = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
if (metadata.name !== 'pinyin-pro' || metadata.version !== '3.29.5') throw Error('Wrong upstream package');
const moduleAt = relative => import(pathToFileURL(path.join(root, relative)).href);
const { default: dictionary } = await moduleAt('dist/esm/data/dict1.mjs');
const { PatternsNormal } = await moduleAt('dist/esm/data/patterns.mjs');
const { getPinyinWithoutTone } = await moduleAt('dist/esm/core/pinyin/handle.mjs');
const characters = [];
for (let cp = 0; cp <= 0x10ffff; cp++) {
  if (cp >= 0xd800 && cp <= 0xdfff) continue;
  const character = String.fromCodePoint(cp);
  const value = dictionary.get(character);
  if (value) characters.push([character, value.split(' ').map(getPinyinWithoutTone)]);
}
const patterns = PatternsNormal.filter(item => item.priority === 1).map((item, order) => ({
  source: item.zh, readings: item.pinyin.split(' ').map(getPinyinWithoutTone),
  probability: item.probability, priority: item.priority, order,
}));
if (patterns.some(item => Array.from(item.source).length !== item.readings.length)) {
  throw Error('Phrase does not preserve scalar alignment');
}
const data = {
  schema: 'vipi-pinyin-pro-ordinary-1',
  upstream: {
    package: 'pinyin-pro', version: '3.29.5',
    archive_sha256: '00e9d2961bb0ba2d247ba5090c242ecbf3793473c9f66f0c69af7248dd4616b4',
    license: 'MIT', copyright: '2022-present zh-lx',
  },
  policy: {
    tone: 'none', surname: 'off', unknown_probability: 1e-13,
    conversion: 'Only tone marks removed from phonetic table values using upstream getPinyinWithoutTone; ü and ê retained, source/protected literal bytes never normalized.',
    special_rules: [
      'At start or immediately after a character absent from DICT1, unmatched 了 becomes liao.',
      'Unmatched 々 repeats previous DICT1 first reading, otherwise tong.',
      '一/不 tone sandhi changes no ordinary tone-free syllable.',
    ],
    selection: 'Upstream max-probability nonoverlapping phrase selection. Character defaults retain all alternative readings in this artifact; default is first, not a contextual certainty claim.',
  },
  characters, patterns,
};
const encoded = JSON.stringify(data) + '\n';
fs.writeFileSync(output, encoded, { flag: 'wx' });
console.log(JSON.stringify({
  characters: characters.length, patterns: patterns.length, bytes: Buffer.byteLength(encoded),
  sha256: crypto.createHash('sha256').update(encoded).digest('hex'),
}));
