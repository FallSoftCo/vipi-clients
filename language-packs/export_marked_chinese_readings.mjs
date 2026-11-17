// Project the retained MIT pinyin-pro package without discarding tone marks.
// No dependency installation, network, shared runtime or guessed Latin tones.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';
if (process.argv.length !== 5) throw Error('Usage: node export_marked_chinese_readings.mjs PACKAGE_DIRECTORY REVIEWED_WORDS OUTPUT');
const root = path.resolve(process.argv[2]);
const metadata = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
if (metadata.name !== 'pinyin-pro' || metadata.version !== '3.29.5') throw Error('Wrong pinned package');
const moduleAt = relative => import(pathToFileURL(path.join(root, relative)).href);
const { default: dictionary } = await moduleAt('dist/esm/data/dict1.mjs');
const { PatternsNormal } = await moduleAt('dist/esm/data/patterns.mjs');
const characters = [];
for (let cp = 0; cp <= 0x10ffff; cp++) {
  if (cp >= 0xd800 && cp <= 0xdfff) continue;
  const source = String.fromCodePoint(cp), value = dictionary.get(source);
  if (value) characters.push([source, value.split(' ')]);
}
const patterns = PatternsNormal.filter(x => x.priority === 1).map((x, order) => ({
  source:x.zh, readings:x.pinyin.split(' '), probability:x.probability, priority:x.priority, order,
}));
const reviewedBytes = fs.readFileSync(process.argv[3]);
const reviewed = JSON.parse(reviewedBytes);
if (reviewed.schema !== 'vipi-chinese-reviewed-words-1') throw Error('Wrong reviewed word schema');
const words = [];
for (const item of reviewed.words) {
  const phrase = patterns.find(x => x.source === item.simplified);
  const readings = phrase?.readings ?? Array.from(item.simplified, c => dictionary.get(c)?.split(' ')[0]);
  if (readings.some(x => !x)) throw Error('Unattested reading');
  for (const source of [item.simplified, item.traditional].filter(Boolean)) {
    if (Array.from(source).length !== readings.length) throw Error('Misaligned alias');
    words.push({source, readings, capitalized:!!item.capitalized});
    // Explicit traditional aliases carry the exact source phrase pronunciation.
    if (source !== item.simplified && !patterns.some(x => x.source === source))
      patterns.push({source, readings, probability:phrase?.probability ?? 2e-8, priority:1, order:patterns.length});
  }
}
const data = {
  schema:'vipi-pinyin-pro-marked-2',
  upstream:{package:'pinyin-pro',version:'3.29.5',archive_sha256:'00e9d2961bb0ba2d247ba5090c242ecbf3793473c9f66f0c69af7248dd4616b4',license:'MIT',copyright:'2022-present zh-lx'},
  policy:{tone:'marked-dictionary',surname:'off',unknown_probability:1e-13,
    conversion:'Original marked dictionary syllables preserved byte-for-byte, including ü, combining marks and neutral tones. Original/protected text unchanged.',
    special_rules:['Unmatched 了 after no dictionary character is liǎo.','々 repeats the previous dictionary first reading, otherwise tóng.','Dictionary underlying tones; no blanket third-tone or 一/不 surface-sandhi rewrite.'],
    selection:'Pinned upstream phrase probability/tie selection plus bounded explicit traditional phrase aliases. Character defaults are not contextual certainty.',
    word_joins:'Reviewed words join only when selected reading syllables match; other boundaries remain syllable-separated.',
    reviewed_words_sha256:crypto.createHash('sha256').update(reviewedBytes).digest('hex')},
  characters,patterns,words,
};
const bytes=JSON.stringify(data)+'\n';
fs.writeFileSync(process.argv[4],bytes,{flag:'wx'});
console.log(JSON.stringify({characters:characters.length,patterns:patterns.length,words:words.length,bytes:Buffer.byteLength(bytes),sha256:crypto.createHash('sha256').update(bytes).digest('hex')}));
