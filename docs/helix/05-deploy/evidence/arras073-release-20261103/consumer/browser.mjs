import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium } from '@playwright/test';
import * as ui from '@documentdrivendx/arras-ui';

assert.equal(typeof ui.ArrasConsole, 'function');
const browser = await chromium.launch({headless: true});
try {
  const context = await browser.newContext({colorScheme: 'dark'});
  const page = await context.newPage();
  await page.addInitScript(() => localStorage.setItem('public-host-marker', 'preserve-me'));
  await page.goto(process.argv[2], {waitUntil: 'networkidle'});
  await page.locator('.arras-root').first().waitFor();
  const observe = () => page.evaluate(() => ({
    appearance: document.documentElement.dataset.appearance,
    marker: getComputedStyle(document.querySelector('.arras-root')).getPropertyValue('--arras-public-theme-proof').trim(),
    surface: getComputedStyle(document.querySelector('.arras-root')).getPropertyValue('--surface').trim(),
    hostStorage: localStorage.getItem('public-host-marker')
  }));
  const before = await observe();
  assert.equal(before.appearance, 'light');
  assert.equal(before.marker, 'public-073');
  assert.equal(before.surface, '#123456');
  await page.emulateMedia({colorScheme: 'light'});
  await page.emulateMedia({colorScheme: 'dark'});
  assert.deepEqual(await observe(), before);
  const negative = await context.newPage();
  await negative.route('**/theme-assets/**', route => route.fulfill({status: 200, contentType: 'text/css', body: ''}));
  await negative.goto(process.argv[2], {waitUntil: 'networkidle'});
  await negative.locator('.arras-root').first().waitFor();
  const blockedMarker = await negative.evaluate(() => getComputedStyle(document.querySelector('.arras-root')).getPropertyValue('--arras-public-theme-proof').trim());
  assert.notEqual(blockedMarker, 'public-073');
  const result = {schema: 'arras.public-stock-theme-browser/1', status: 'passed', browserVersion: browser.version(), declaredAppearance: before.appearance, actualSurface: before.surface, osChangesPreserveHostDeclaration: true, hostStoragePreserved: true, missingStylesheetControl: true, publicNpmRootExports: Object.keys(ui).sort()};
  fs.writeFileSync(process.argv[3], JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
