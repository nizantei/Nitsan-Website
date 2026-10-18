// Close-up screenshots of the character at each page station, rendered with three.js in
// headless Chromium (viewer.html). Needs the dev server: cd work/tools && npm run serve
// Run:  node stations.mjs [outDir] [src]   → <outDir>/station-<view>.png + stations.png sheet
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const out = process.argv[2] || 'build/preview/stations';
const src = process.argv[3] || '/work/models/nitsan.glb';
const base = process.env.BASE || 'http://localhost:8080';
const views = ['full', 'three-quarter', 'face', 'face-34', 'chest', 'hands', 'belt', 'knees', 'feet', 'back'];
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM || undefined,
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage({ viewport: { width: 960, height: 600 }, deviceScaleFactor: 1 });
page.on('pageerror', (e) => console.error('pageerror', e.message));
for (const view of views) {
  await page.goto(`${base}/work/tools/model/viewer.html?view=${view}&src=${encodeURIComponent(src)}`);
  await page.waitForSelector('body[data-ready]', { timeout: 120000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}/station-${view}.png` });
  console.log('shot', view);
}
await browser.close();
