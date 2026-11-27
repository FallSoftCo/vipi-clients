// Private browser QA on OZZZ-OS; no shared profile or desktop.
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
const { chromium } = await import(process.env.EIGHTBAR_PLAYWRIGHT_MODULE);
const root = process.env.VIPI_GALLERY_RECEIPTS;
assert(root?.startsWith('/aosp/development/vipi/artifacts/'));
await mkdir(root, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  headless: true,
  args: ['--no-sandbox', '--disable-http2'],
});
const base = 'https://system76-pc.tailb77f2a.ts.net/8bar/';
try {
  const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  await page.goto(base, { waitUntil: 'domcontentloaded', timeout: 120000 });
  const results = [];
  for (const id of [
    'vipi-ios-immersion-20261024',
    'vipi-android-immersion-20261024',
    'vipi-ios-dark-immersion-20261024',
  ]) {
    const card = page.locator('#' + id);
    await card.waitFor({ timeout: 60000 });
    await card.scrollIntoViewIfNeeded();
    await card.locator('.stage img').evaluate((img) =>
      img.complete && img.naturalWidth > 0
        ? true
        : new Promise((resolve, reject) => {
            img.onload = resolve;
            img.onerror = reject;
          }),
    );
    await card.screenshot({ path: `${root}/${id}.png` });
    results.push({ id, visible: await card.isVisible() });
  }
  for (const file of [
    'ios-light.png',
    'ios-dark.png',
    'android-light.png',
    'ios-speech.wav',
    'android-speech.wav',
    'scope.json',
  ]) {
    const response = await page.request.get(base + 'vipi-immersion-20261024/' + file);
    assert(response.ok(), `${file}: ${response.status()}`);
    assert((await response.body()).length > 50);
  }
  const receipt = {
    status: 'passed',
    timestamp: new Date().toISOString(),
    revision: await page.locator('html').getAttribute('data-gallery-revision'),
    cards: results,
  };
  await writeFile(`${root}/receipt.json`, JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify(receipt));
} finally {
  await browser.close();
}
