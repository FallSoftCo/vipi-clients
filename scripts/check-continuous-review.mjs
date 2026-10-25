// Inspect the delivered native evidence using a private browser on OZZZ-OS.
import assert from 'node:assert/strict';
import {mkdir, writeFile} from 'node:fs/promises';
const {chromium} = await import(process.env.EIGHTBAR_PLAYWRIGHT_MODULE);
const root = process.env.VIPI_GALLERY_RECEIPTS;
assert(root?.startsWith('/aosp/development/vipi/artifacts/'));
await mkdir(root, {recursive: true});
const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, headless: true, args: ['--no-sandbox', '--disable-http2']});
const base = 'https://system76-pc.tailb77f2a.ts.net/8bar/';
const category = 'vipi-continuous-20261024';
const languages = ['en', 'es', 'fr', 'de', 'it', 'pt', 'ar', 'zh', 'ja', 'ko'];
const checks = [];
try {
  const page = await browser.newPage({viewport: {width: 1100, height: 900}});
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.goto(`${base}${category}/matrix/review.html`, {waitUntil: 'domcontentloaded'});
  for (const platform of ['android', 'ios']) {
    await page.locator('#platform').selectOption(platform);
    for (const source of languages) for (const target of languages.filter(value => value !== source)) {
      await page.locator('#source').selectOption(source);
      await page.locator('#target').selectOption(target);
      for (const phase of ['target', 'meaning', 'script']) {
        await page.locator(`[data-phase="${phase}"]`).click();
        const name = `${platform}/${source}-${target}-${phase}.png`;
        await page.waitForFunction(name => {const img = document.querySelector('#capture'); return img.src.endsWith(name) && img.complete && img.naturalWidth > 0 && img.naturalHeight > 0;}, name);
      }
      checks.push({platform, source, target});
    }
  }
  await page.locator('#source').selectOption('en'); await page.locator('#target').selectOption('ja');
  await page.locator('[data-phase="target"]').click();
  await page.locator('#play').click();
  await page.waitForFunction(() => document.querySelector('#capture').src.endsWith('-meaning.png'), undefined, {timeout: 7000});
  await page.locator('#play').click();
  for (const width of [1100, 390]) {
    await page.setViewportSize({width, height: 900});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({path: `${root}/matrix-${width}.png`, fullPage: true});
  }
  assert.deepEqual(errors, []);
  await page.goto(base, {waitUntil: 'domcontentloaded', timeout: 120000});
  const cards = ['vipi-ios-continuous-20261024', 'vipi-android-continuous-20261024', 'vipi-reading-matrix-20261024'];
  for (const id of cards) {
    const card = page.locator('#' + id); await card.waitFor({timeout: 60000}); await card.scrollIntoViewIfNeeded();
    await card.locator('.stage img').evaluate(img => img.complete && img.naturalWidth > 0 ? true : new Promise((resolve, reject) => {img.onload = resolve; img.onerror = reject;}));
    await card.screenshot({path: `${root}/${id}.png`});
  }
  const media = [];
  for (const platform of ['ios', 'android']) {
    const url = `${base}${category}/${platform}-continuous.mp4`;
    await page.goto(url, {waitUntil: 'domcontentloaded'});
    const video = page.locator('video');
    await video.evaluate(async value => {value.muted = true; await value.play();});
    await page.waitForFunction(() => {const value = document.querySelector('video'); return value.currentTime > 0.5 && value.duration > 20;});
    media.push(await video.evaluate(value => {value.pause(); return {src: value.src, duration: value.duration, width: value.videoWidth, height: value.videoHeight};}));
  }
  const receipt = {status: 'passed', timestamp: new Date().toISOString(), scope: 'native evidence viewer and three Vipi gallery cards; not whole-gallery health', checks, cards, media};
  await writeFile(`${root}/receipt.json`, JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify({status: receipt.status, directions: checks.length, cards, media}));
} finally { await browser.close(); }
