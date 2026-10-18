// Headless check of /work/: loads the page in each mode, plays the Start zoom, visits every
// station, reports console errors, and saves screenshots. Needs a local server on :8080
// (npm run serve). Run:  npm run shots -- [outDir]     (ONLY=desktop,mobile,... to pick jobs)
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const BASE = process.env.WORK_URL || 'http://localhost:8080/work/';
const out = process.argv[2] || 'shots';
const WAIT = +(process.env.WAIT || 2200);
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM || undefined,
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
});

// Scroll targets come from the live director (exposed with ?debug).
const station = (i) => `__work.director.chapterY(${i})`;
const beat = (i, b) => `__work.director.beatY(${i}, ${b})`;
const travel = (i, t) => `(() => { const s = __work.director.stops; return s[${i}].end + (s[${i + 1}].start - s[${i}].end) * ${t}; })()`;

async function run(name, { viewport, query = '', reducedMotion = 'no-preference', isMobile = false, steps }) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, reducedMotion, isMobile, hasTouch: isMobile });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`${m.type()}: ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  await page.goto(BASE + query, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.documentElement.classList.contains('is-loaded'), null, { timeout: 90000 });
  await page.waitForTimeout(3500); // intro materialize
  const info = await page.evaluate(() => ({ classes: document.documentElement.className, height: document.documentElement.scrollHeight }));
  console.log(`\n[${name}] ${info.classes} scrollHeight=${info.height}`);

  const shot = async (label) => {
    await page.evaluate(() => window.__work?.settle());
    await page.waitForTimeout(700);
    const hud = await page.evaluate(() => document.querySelector('.hud')?.textContent || '');
    await page.screenshot({ path: `${out}/${name}-${label}.png` });
    console.log(`  ${label}: ${hud.split('\n').slice(1, 3).join(' | ')}`);
  };
  for (const [label, action] of steps) {
    if (action === 'start') {
      await page.click('[data-start]');
      continue;
    }
    if (typeof action === 'number') { await page.waitForTimeout(action); await shot(label); continue; }
    if (action) {
      const y = Math.round(await page.evaluate(action));
      await page.evaluate((top) => window.scrollTo(0, top), y);
      await page.waitForTimeout(WAIT);
    }
    await shot(label);
  }
  console.log(errors.length ? errors.map((e) => '  ! ' + e).join('\n') : '  no console errors');
  await ctx.close();
}

const cinematic = [
  ['00-hero', null],
  ['', 'start'],
  ['01-zoom', 900],
  ['02-face', 3200],
  ['03-apps-pair2', beat(0, 1)],
  ['04-travel', travel(1, 0.5)],
  ['05-talks-pair1', beat(1, 0)],
  ['06-talks-pair2', beat(1, 1)],
  ['07-skills-pair1', beat(2, 0)],
  ['08-certs-pair1', beat(3, 0)],
  ['09-certs-pair3', beat(3, 2)],
  ['10-outro', '__work.director.maxScroll'],
];
const quick = [['00-hero', null], ['', 'start'], ['02-face', 3600], ['05-talks', beat(1, 0)], ['07-skills', beat(2, 0)], ['08-certs', beat(3, 0)]];
const mobile = [
  ['00-hero', null],
  ['', 'start'],
  ['02-face', 3800],
  ['03-apps-item2', beat(0, 1)],
  ['05-talks-item1', beat(1, 0)],
  ['07-skills-item1', beat(2, 0)],
  ['08-certs-item1', beat(3, 0)],
  ['10-outro', '__work.director.maxScroll'],
];
const flow = [['00-top', null], ['01-apps', station(0)], ['02-skills', station(2)], ['03-end', '__work.director.maxScroll']];

const only = process.env.ONLY;
const Q = process.env.QUALITY || 'high';
const jobs = {
  desktop: () => run('desktop', { viewport: { width: 1440, height: 900 }, query: `?debug&quality=${Q}`, steps: cinematic }),
  wide: () => run('wide', { viewport: { width: 1920, height: 1080 }, query: `?debug&quality=${Q}`, steps: quick }),
  small: () => run('small', { viewport: { width: 1280, height: 720 }, query: `?debug&quality=${Q}`, steps: quick }),
  mobile: () => run('mobile', { viewport: { width: 390, height: 844 }, query: '?debug', isMobile: true, steps: mobile }),
  reduced: () => run('reduced', { viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', query: '?debug', steps: flow }),
  poster: () => run('poster', { viewport: { width: 1440, height: 900 }, query: '?mode=poster&debug', steps: flow }),
};
for (const [k, job] of Object.entries(jobs)) if (!only || only.split(',').includes(k)) await job();
await browser.close();
