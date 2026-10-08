// Headless check of /work/: loads the page in each mode, reports console errors, and saves
// screenshots along the scroll. Needs a local server on :8080 (npm run serve).
// Run:  npm run shots -- [outDir]
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const BASE = process.env.WORK_URL || 'http://localhost:8080/work/';
const out = process.argv[2] || 'shots';
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM || undefined,
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
});

async function run(name, { viewport, query = '', reducedMotion = 'no-preference', stops, isMobile = false }) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, reducedMotion, isMobile, hasTouch: isMobile });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`${m.type()}: ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  await page.goto(BASE + query, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.documentElement.classList.contains('is-loaded'), null, { timeout: 60000 });
  await page.waitForTimeout(3500); // intro materialize
  const info = await page.evaluate(() => ({
    classes: document.documentElement.className,
    height: document.documentElement.scrollHeight,
    vh: innerHeight,
  }));
  console.log(`\n[${name}] ${info.classes} scrollHeight=${info.height}`);
  for (const [label, frac] of stops) {
    const y = Math.round(await page.evaluate(frac));
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await page.waitForTimeout(+(process.env.WAIT || 2600));
    const hud = await page.evaluate(() => document.querySelector('.hud')?.textContent || '');
    await page.screenshot({ path: `${out}/${name}-${label}.png` });
    console.log(`  ${label} y=${y} ${hud.split('\n').slice(1, 3).join(' | ')}`);
  }
  console.log(errors.length ? errors.map((e) => '  ! ' + e).join('\n') : '  no console errors');
  await ctx.close();
}

// Scroll targets come from the live director (exposed with ?debug).
const chapter = (i) => `__work.director.chapterY(${i})`;
const item = (i, j) => `__work.director.beatY(${i}, ${j})`;
const lead = (id) => `document.querySelector('#${id} .chapter__lead').getBoundingClientRect().top + scrollY`;
const stops = [
  ['0-hero', '0'],
  ['1-travel', lead('apps')],
  ['2-apps-intro', chapter(0)],
  ['3-apps-item2', item(0, 1)],
  ['4-talks-item1', item(1, 0)],
  ['5-skills-intro', chapter(2)],
  ['6-skills-item3', item(2, 2)],
  ['7-certs-item1', item(3, 0)],
  ['8-outro', '__work.director.maxScroll'],
];
const staticStops = [['0-top', '0'], ['1-apps', chapter(0)], ['2-skills', chapter(2)], ['3-end', '__work.director.maxScroll']];

const only = process.env.ONLY;
const jobs = {
  desktop: () => run('desktop', { viewport: { width: 1440, height: 900 }, query: '?debug&quality=high', stops }),
  mobile: () => run('mobile', { viewport: { width: 390, height: 844 }, query: '?debug', stops, isMobile: true }),
  reduced: () => run('reduced', { viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', query: '?debug', stops: staticStops }),
  poster: () => run('poster', { viewport: { width: 1440, height: 900 }, query: '?mode=poster&debug', stops: staticStops }),
};
for (const [k, job] of Object.entries(jobs)) if (!only || only.split(',').includes(k)) await job();
await browser.close();
