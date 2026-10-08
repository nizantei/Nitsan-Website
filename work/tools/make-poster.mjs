// Renders the hero figure on a transparent background and saves it as /work/media/poster.webp,
// the still image shown when WebGL is unavailable. Re-run after changing the model.
// Needs a local server on :8080 (npm run serve).  Run:  npm run poster
import { chromium } from 'playwright';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const URL_ = (process.env.WORK_URL || 'http://localhost:8080/work/') + '?mode=cinematic&quality=high';
const out = fileURLToPath(new URL('../media/poster.webp', import.meta.url));

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM || undefined,
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage({ viewport: { width: 1000, height: 1200 }, deviceScaleFactor: 1 });
await page.goto(URL_, { waitUntil: 'networkidle' });
await page.waitForFunction(() => document.documentElement.classList.contains('is-loaded'), null, { timeout: 60000 });
await page.waitForTimeout(9000); // let the intro finish, even with software rendering
await page.addStyleTag({ content: '.backdrop,.labels,main,.topbar,.hud,.loader{display:none!important}html,body{background:transparent!important}' });
await page.waitForTimeout(500);
const png = await page.screenshot({ omitBackground: true });

// Encode to WebP in the browser (keeps alpha, no extra dependencies).
const webp = await page.evaluate(async (b64) => {
  const img = new Image();
  img.src = `data:image/png;base64,${b64}`;
  await img.decode();
  const c = document.createElement('canvas');
  c.width = img.width; c.height = img.height;
  c.getContext('2d').drawImage(img, 0, 0);
  return c.toDataURL('image/webp', 0.86).split(',')[1];
}, png.toString('base64'));
writeFileSync(out, Buffer.from(webp, 'base64'));
console.log('wrote', out, Math.round(Buffer.from(webp, 'base64').length / 1024) + ' KB');
await browser.close();
