// Scene helpers: texture cache, generated label textures, rounded panels, DOM labels.
import * as THREE from 'three';
import { asset } from '../util.js';

export function createTextures(renderer, { onChange } = {}) {
  const loader = new THREE.TextureLoader();
  const cache = new Map();
  const anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());

  function get(path, onLoad) {
    let tex = cache.get(path);
    if (!tex) {
      tex = loader.load(asset(path), (t) => {
        t.userData.waiting.forEach((cb) => cb(t));
        t.userData.waiting = [];
        onChange?.();
      }, undefined, () => console.warn('[work] texture failed:', path));
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = anisotropy;
      tex.userData.waiting = [];
      cache.set(path, tex);
    }
    if (onLoad) tex.image ? onLoad(tex) : tex.userData.waiting.push(onLoad);
    return tex;
  }

  // Fallback texture for items without an image: the title on a gradient card.
  function label(text, { w = 1024, h = 640, a = '#00d4ff', b = '#ff006e' } = {}) {
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    const g = c.getContext('2d');
    const grad = g.createLinearGradient(0, 0, w, h);
    grad.addColorStop(0, '#11163a'); grad.addColorStop(1, '#05060d');
    g.fillStyle = grad; g.fillRect(0, 0, w, h);
    g.strokeStyle = a; g.lineWidth = 6; g.strokeRect(3, 3, w - 6, h - 6);
    g.fillStyle = '#ffffff';
    g.font = `700 ${Math.round(h * 0.13)}px "Space Grotesk", system-ui, sans-serif`;
    g.textBaseline = 'middle';
    wrap(g, text, w * 0.08, h * 0.5, w * 0.84, h * 0.15);
    g.fillStyle = b; g.fillRect(w * 0.08, h * 0.8, w * 0.18, 8);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = anisotropy;
    return tex;
  }

  return { get, label };
}

function wrap(g, text, x, y, maxW, lineH) {
  const words = String(text).split(' ');
  const lines = [];
  let line = '';
  for (const word of words) {
    const test = line ? `${line} ${word}` : word;
    if (g.measureText(test).width > maxW && line) { lines.push(line); line = word; } else line = test;
  }
  lines.push(line);
  const top = y - ((lines.length - 1) * lineH) / 2;
  lines.forEach((l, i) => g.fillText(l, x, top + i * lineH));
}

// Rounded rectangle with 0..1 UVs across its bounds (ShapeGeometry UVs are in shape units).
export function roundedRect(w, h, r) {
  const s = new THREE.Shape();
  const x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  const g = new THREE.ShapeGeometry(s, 8);
  const pos = g.attributes.position, uv = g.attributes.uv;
  for (let i = 0; i < pos.count; i++) uv.setXY(i, (pos.getX(i) - x) / w, (pos.getY(i) - y) / h);
  return g;
}

// DOM labels pinned to 3D points (crisp text, no font atlas). Pooled; hidden when unused.
export function createLabels(layer) {
  const pool = [];
  const v = new THREE.Vector3();
  let used = 0;
  return {
    begin() { used = 0; },
    add(text, worldPos, camera, size, alpha) {
      v.copy(worldPos).project(camera);
      if (v.z > 1 || alpha <= 0.01) return;
      let el = pool[used];
      if (!el) {
        el = document.createElement('span');
        el.className = 'label';
        layer.appendChild(el);
        pool.push(el);
      }
      if (el.textContent !== text) el.textContent = text;
      const x = (v.x * 0.5 + 0.5) * size.x;
      const y = (-v.y * 0.5 + 0.5) * size.y;
      el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -150%)`;
      el.style.opacity = alpha.toFixed(3);
      used++;
    },
    end() {
      for (let i = used; i < pool.length; i++) if (pool[i].style.opacity !== '0') pool[i].style.opacity = '0';
    },
  };
}
