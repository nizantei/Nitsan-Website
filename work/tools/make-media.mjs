// Generates the placeholder cover images referenced by data/content.json (SVG, a few KB each).
// Real images can be any web format (webp/jpg/png/svg); just point `image` at the file.
// Run:  npm run media
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const dir = fileURLToPath(new URL('../media/placeholder/', import.meta.url));
mkdirSync(dir, { recursive: true });

const PALETTES = [
  ['#00d4ff', '#3a2bff'], ['#ff006e', '#8338ec'], ['#06ffa5', '#00a3ff'],
  ['#ffbe0b', '#ff006e'], ['#8338ec', '#00d4ff'],
];

function cover(file, { w, h, title, kicker, palette, kind }) {
  const [a, b] = palette;
  const grid = Array.from({ length: 14 }, (_, i) =>
    `<line x1="${(i + 1) * w / 15}" y1="0" x2="${(i + 1) * w / 15}" y2="${h}"/>`).join('');
  const shape = kind === 'talk'
    ? `<circle cx="${w * 0.78}" cy="${h * 0.42}" r="${h * 0.3}" fill="url(#g)" opacity=".85"/>
       <rect x="${w * 0.08}" y="${h * 0.62}" width="${w * 0.36}" height="10" rx="5" fill="#fff" opacity=".35"/>
       <rect x="${w * 0.08}" y="${h * 0.62 + 30}" width="${w * 0.24}" height="10" rx="5" fill="#fff" opacity=".2"/>`
    : `<rect x="${w * 0.62}" y="${h * 0.12}" width="${h * 0.42}" height="${h * 0.76}" rx="36" fill="#0b1030" stroke="url(#g)" stroke-width="6"/>
       <rect x="${w * 0.62 + 26}" y="${h * 0.12 + 60}" width="${h * 0.42 - 52}" height="${h * 0.22}" rx="18" fill="url(#g)" opacity=".9"/>
       <rect x="${w * 0.62 + 26}" y="${h * 0.42}" width="${h * 0.3}" height="14" rx="7" fill="#fff" opacity=".4"/>
       <rect x="${w * 0.62 + 26}" y="${h * 0.42 + 34}" width="${h * 0.22}" height="14" rx="7" fill="#fff" opacity=".22"/>`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient>
    <radialGradient id="bg" cx=".3" cy=".2" r="1"><stop offset="0" stop-color="#1a2150"/><stop offset="1" stop-color="#05060d"/></radialGradient>
  </defs>
  <rect width="${w}" height="${h}" fill="url(#bg)"/>
  <g stroke="#ffffff" stroke-opacity=".05" stroke-width="2">${grid}</g>
  ${shape}
  <text x="${w * 0.08}" y="${h * 0.2}" fill="${a}" font-family="ui-monospace, Menlo, monospace" font-size="${h * 0.045}" letter-spacing="4">${kicker}</text>
  <text x="${w * 0.08}" y="${h * 0.5}" fill="#ffffff" font-family="system-ui, -apple-system, Segoe UI, sans-serif" font-weight="700" font-size="${h * 0.14}">${title}</text>
  <text x="${w * 0.08}" y="${h * 0.9}" fill="#ffffff" fill-opacity=".45" font-family="ui-monospace, Menlo, monospace" font-size="${h * 0.035}" letter-spacing="3">PLACEHOLDER IMAGE</text>
</svg>`;
  writeFileSync(dir + file, svg);
}

function badge(file, { title, palette }) {
  const [a, b] = palette;
  const s = 800;
  const ticks = Array.from({ length: 60 }, (_, i) => {
    const t = (i / 60) * Math.PI * 2;
    const r1 = 330, r2 = i % 5 ? 345 : 360;
    return `<line x1="${400 + Math.cos(t) * r1}" y1="${400 + Math.sin(t) * r1}" x2="${400 + Math.cos(t) * r2}" y2="${400 + Math.sin(t) * r2}"/>`;
  }).join('');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${s}" height="${s}" viewBox="0 0 ${s} ${s}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient>
    <radialGradient id="bg" cx=".5" cy=".4" r=".7"><stop offset="0" stop-color="#1b2257"/><stop offset="1" stop-color="#070a1c"/></radialGradient>
  </defs>
  <rect width="${s}" height="${s}" fill="url(#bg)"/>
  <circle cx="400" cy="400" r="300" fill="none" stroke="url(#g)" stroke-width="14"/>
  <g stroke="#fff" stroke-opacity=".35" stroke-width="4">${ticks}</g>
  <text x="400" y="440" text-anchor="middle" fill="#fff" font-family="system-ui, -apple-system, Segoe UI, sans-serif" font-weight="700" font-size="150">${title}</text>
  <text x="400" y="540" text-anchor="middle" fill="${a}" font-family="ui-monospace, Menlo, monospace" font-size="34" letter-spacing="6">SAMPLE</text>
</svg>`;
  writeFileSync(dir + file, svg);
}

const apps = [['app-atlas.svg', 'Atlas'], ['app-pulse.svg', 'Pulse'], ['app-harbor.svg', 'Harbor'], ['app-lumen.svg', 'Lumen']];
apps.forEach(([file, title], i) => cover(file, { w: 1600, h: 1000, title, kicker: 'SAMPLE APP', palette: PALETTES[i], kind: 'app' }));

const talks = [['talk-3d-web.svg', '3D on the web'], ['talk-shipping.svg', 'Ship fast'], ['talk-app-store.svg', 'Idea → Store']];
talks.forEach(([file, title], i) => cover(file, { w: 1600, h: 900, title, kicker: 'SAMPLE TALK', palette: PALETTES[(i + 2) % 5], kind: 'talk' }));

const certs = [['cert-cloud.svg', 'CL'], ['cert-security.svg', 'SE'], ['cert-ux.svg', 'UX'], ['cert-leadership.svg', 'LD'], ['cert-data.svg', 'DA']];
certs.forEach(([file, title], i) => badge(file, { title, palette: PALETTES[i] }));

console.log('placeholder media written to', dir);
