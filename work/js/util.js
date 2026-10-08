// Small math and DOM helpers shared by the page and the 3D scene.

export const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
export const lerp = (a, b, t) => a + (b - a) * t;
// Frame-rate independent exponential smoothing toward a target.
export const damp = (a, b, lambda, dt) => lerp(a, b, 1 - Math.exp(-lambda * dt));
export const smoothstep = (a, b, v) => { const t = clamp((v - a) / (b - a)); return t * t * (3 - 2 * t); };
export const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
export const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);
export const easeOutBack = (t, s = 1.5) => 1 + (s + 1) * Math.pow(t - 1, 3) + s * Math.pow(t - 1, 2);

// Per-element progress for a staggered group: element i starts later than element i-1.
export function stagger(p, i, n, spread = 0.5) {
  if (n <= 1) return clamp(p);
  const start = (i / (n - 1)) * spread;
  return clamp((p - start) / (1 - spread));
}

// All data paths (images, models) are relative to /work/, wherever the page URL ends
// (/work and /work/ resolve relative URLs differently, so never resolve against the page).
export const BASE = new URL('../', import.meta.url);
export const asset = (path) => new URL(path, BASE).href;

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (s = '') => String(s).replace(/[&<>"']/g, (c) => ESC[c]);

export const safeUrl = (url = '#') => (/^\s*javascript:/i.test(url) ? '#' : url);
export const pad = (n) => String(n).padStart(2, '0');
