import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import net from 'node:net';
import crypto from 'node:crypto';
import { spawn, execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';
const root = '/aosp/development/vipi';
assert.equal(os.hostname(), 'ozzz-aosp');
const revision = process.argv[2];
assert.match(revision, /^\d{3}$/);
const output = path.join(root, 'artifacts', `deletion-web-ui-${revision}`);
await fs.mkdir(output);
const work = path.join(root, '.runtime', `deletion-web-ui-${revision}`);
await fs.mkdir(work, { mode: 0o700 });
const listener = net.createServer();
await new Promise((r) => listener.listen(0, '127.0.0.1', r));
const port = listener.address().port;
await new Promise((r) => listener.close(r));
const origin = `https://127.0.0.1:${port}`;
await fs.writeFile(
  path.join(work, 'fixture.json'),
  JSON.stringify({
    origin,
    port,
    account: crypto.randomUUID(),
    secret: crypto.randomBytes(32).toString('base64url'),
  }),
  { mode: 0o600 },
);
execFileSync(
  'openssl',
  [
    'req',
    '-x509',
    '-newkey',
    'rsa:2048',
    '-nodes',
    '-keyout',
    path.join(work, 'key.pem'),
    '-out',
    path.join(work, 'cert.pem'),
    '-days',
    '1',
    '-subj',
    '/CN=localhost',
  ],
  { stdio: 'ignore' },
);
await fs.chmod(path.join(work, 'key.pem'), 0o600);
const python = path.join(root, 'backend/.venv/bin/python');
const server = spawn(python, [path.join(root, 'scripts/serve-web-deletion-qa.py'), work], {
  stdio: ['ignore', 'ignore', 'pipe'],
});
let serverErrors = '';
server.stderr.on('data', (d) => (serverErrors += d.toString()));
const { chromium } =
  await import('/aosp/houdini/8bar-product-demo-20261022-r01/node_modules/playwright-core/index.mjs');
const browser = await chromium.launch({
  executablePath: '/home/aosp/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome',
  headless: true,
  args: ['--no-sandbox'],
});
const receipt = {
  real_provider: false,
  network: 'loopback TLS only; provider intercepted',
  passed: false,
  checks: [],
  screens: [],
};
let currentPage;
const errors = [];
try {
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    viewport: { width: 1100, height: 900 },
  });
  const page = await context.newPage();
  currentPage = page;
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    if (m.type() === 'error' && !m.text().includes('favicon')) errors.push(m.text());
  });
  page.on('request', (request) => {
    if (request.method() === 'POST')
      receipt.lastPost = {
        path: new URL(request.url()).pathname,
        origin: request.headers().origin,
        contentType: request.headers()['content-type'],
        fetchSite: request.headers()['sec-fetch-site'],
      };
  });
  await context.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) {
      errors.push('Unexpected external origin: ' + url.origin);
      return route.abort();
    }
    if (url.pathname !== '/delete-account/sign-in') return route.continue();
    // Playwright routes only the first request of a redirect chain. Stop that
    // chain at the fixture's own redirect, before any external provider call.
    const response = await route.fetch({ maxRedirects: 0 });
    const target = new URL(response.headers().location);
    assert.equal(target.origin, 'https://api.workos.com');
    assert.equal(target.pathname, '/user_management/authorize');
    assert.equal(target.searchParams.get('max_age'), '0');
    const callback = new URL(target.searchParams.get('redirect_uri'));
    callback.searchParams.set('state', target.searchParams.get('state'));
    callback.searchParams.set('code', 'browser-fixture');
    await route.fulfill({ response, headers: { ...response.headers(), location: callback.href } });
  });
  const deadline = Date.now() + 15000;
  while (true) {
    try {
      const r = await context.request.get(origin + '/health/live');
      if (r.ok()) break;
    } catch {}
    if (Date.now() > deadline) throw Error('fixture did not start: ' + serverErrors);
    await new Promise((r) => setTimeout(r, 200));
  }
  async function capture(name) {
    assert((await page.locator('h1').count()) === 1);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: path.join(output, name + '.png'), fullPage: true });
    receipt.screens.push(name + '.png');
  }
  await page.goto(origin + '/delete-account');
  await capture('landing-light');
  await page.getByRole('link', { name: 'Sign in to continue', exact: true }).click();
  await page.getByRole('heading', { name: 'Delete your account?', exact: true }).waitFor();
  assert(await page.getByText('@mika', { exact: true }).isVisible());
  await capture('confirm-light');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('heading', { name: 'Deletion canceled', exact: true }).waitFor();
  receipt.checks.push(
    'fresh PKCE redirect with browser CSP',
    'explicit confirmation',
    'cancel preserves account',
  );
  await page.goto(origin + '/delete-account');
  await page.getByRole('link', { name: 'Sign in to continue', exact: true }).click();
  await page.getByRole('heading', { name: 'Delete your account?', exact: true }).waitFor();
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.setViewportSize({ width: 390, height: 844 });
  await capture('confirm-dark-mobile');
  await page.locator('summary').click();
  await capture('details-dark-mobile');
  // 200% text zoom, normal document flow: final controls remain reachable.
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '34px';
    document.querySelectorAll('.lead').forEach((e) => (e.style.fontSize = '38px'));
    document.querySelectorAll('details').forEach((e) => (e.style.fontSize = '30px'));
  });
  await page.getByRole('button', { name: 'Delete account', exact: true }).scrollIntoViewIfNeeded();
  await capture('confirm-large-text');
  await page.getByRole('button', { name: 'Delete account', exact: true }).click();
  await page.getByRole('heading', { name: 'Deletion in progress', exact: true }).waitFor();
  await capture('pending-dark-mobile');
  await page.close();
  const resumed = await context.newPage();
  currentPage = resumed;
  await resumed.goto(origin + '/delete-account');
  await resumed.getByRole('heading', { name: 'Deletion in progress', exact: true }).waitFor();
  execFileSync(python, [path.join(root, 'scripts/serve-web-deletion-qa.py'), work, '--complete'], {
    stdio: 'pipe',
  });
  await resumed.getByRole('link', { name: 'Check status', exact: true }).click();
  await resumed.getByRole('heading', { name: 'Account deleted', exact: true }).waitFor();
  await resumed.screenshot({ path: path.join(output, 'completed.png'), fullPage: true });
  receipt.screens.push('completed.png');
  const cookies = await context.cookies();
  assert(!cookies.some((c) => c.name === '__Host-vipi-delete-auth'));
  assert(
    cookies.filter((c) => c.name.startsWith('__Host-vipi')).every((c) => c.secure && c.httpOnly),
  );
  receipt.checks.push(
    '200% text controls reachable',
    'resume after tab close',
    'pending becomes completed',
    'sign-in cookie removed',
  );
  receipt.browserErrors = errors;
  assert.deepEqual(errors, []);
  receipt.passed = true;
} catch (error) {
  receipt.failure = error.message;
  receipt.browserErrors = errors;
  if (currentPage && !currentPage.isClosed()) {
    receipt.failurePath = new URL(currentPage.url()).pathname;
    await fs.writeFile(
      path.join(output, 'failure.txt'),
      await currentPage.locator('body').innerText(),
    );
    await currentPage.screenshot({ path: path.join(output, 'failure.png'), fullPage: true });
  }
  throw error;
} finally {
  await browser.close();
  server.kill('SIGTERM');
  await new Promise((resolve) =>
    server.exitCode !== null ? resolve() : server.once('exit', resolve),
  );
  receipt.listener_stopped = true;
  await fs.writeFile(path.join(output, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
  await fs.writeFile(path.join(output, 'fixture-server.log'), serverErrors);
}
console.log(JSON.stringify({ output, passed: receipt.passed, checks: receipt.checks }));
