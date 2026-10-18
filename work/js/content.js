// Loads data/content.json and renders the stations. Adding a work = adding an object to a
// chapter's `items` array (and dropping its image into /work/media/). Adding a chapter = adding
// an object to `chapters`; `station` picks where on the body it sits (head | chest | hands |
// waist | legs | feet) and `reveal` its 3D effect (orbit | stage | constellation | medals).
import { asset, esc, pad, safeUrl, lerp } from './util.js';

const REVEALS = ['orbit', 'stage', 'constellation', 'medals'];

export async function loadContent() {
  const res = await fetch(asset('data/content.json'), { cache: 'no-cache' });
  if (!res.ok) throw new Error(`content.json: HTTP ${res.status}`);
  return res.json();
}

export function normalize(data, config) {
  const list = data.chapters ?? [];
  const stations = resolveStations(list, config.stations);
  const chapters = list.map((ch, i) => {
    const id = slug(ch.id || ch.label || ch.title || `section-${i + 1}`);
    return {
      id,
      index: i,
      num: pad(i + 1),
      label: ch.label || ch.title || id,
      title: ch.title || ch.label || id,
      intro: ch.intro || '',
      reveal: REVEALS.includes(ch.reveal) ? ch.reveal : 'orbit',
      station: stations[i],
      items: (ch.items ?? []).filter((it) => it && it.title).map((it) => ({
        title: it.title,
        meta: it.meta || '',
        description: it.description || '',
        image: it.image || '',
        alt: it.alt ?? '',
        tags: Array.isArray(it.tags) ? it.tags : [],
        links: Array.isArray(it.links) ? it.links.filter((l) => l && l.url) : [],
      })),
    };
  });
  return { meta: data.meta ?? {}, chapters };
}

// Explicit `station` values are kept; the rest are spread down the body in order. With more
// sections than stations, extra ones get in-between heights.
function resolveStations(list, presets) {
  const keys = Object.keys(presets);
  const n = list.length;
  return list.map((ch, i) => {
    if (presets[ch.station]) return { key: ch.station, ...presets[ch.station] };
    const t = n > 1 ? i / (n - 1) : 0;
    if (n <= keys.length) {
      const key = keys[Math.round(t * (keys.length - 1))];
      return { key, ...presets[key] };
    }
    const f = t * (keys.length - 1);
    const a = presets[keys[Math.floor(f)]], b = presets[keys[Math.ceil(f)]];
    const k = f - Math.floor(f);
    const near = k < 0.5 ? a : b;
    return { ...near, key: k < 0.5 ? keys[Math.floor(f)] : keys[Math.ceil(f)], y: lerp(a.y, b.y, k), span: lerp(a.span, b.span, k), width: Math.max(a.width, b.width), up: lerp(a.up, b.up, k) };
  });
}

export function renderContent(content, config) {
  const { meta, chapters } = content;
  const H = config.model.height;

  document.querySelectorAll('[data-meta]').forEach((el) => {
    const value = meta[el.dataset.meta];
    if (value) el.textContent = value;
  });
  if (meta.name) document.title = `${meta.name} · Work`;

  const actions = document.querySelector('[data-outro-actions]');
  if (actions) {
    const mail = meta.email ? `<a class="button button--primary" href="mailto:${esc(meta.email)}">${esc(meta.email)}</a>` : '';
    actions.innerHTML = mail + (meta.links ?? []).map(linkHTML('button')).join('');
  }

  document.querySelector('[data-chapter-nav]').innerHTML = chapters
    .map((ch) => `<li><a href="#${ch.id}" data-nav="${ch.index}"><span>${ch.num}</span><b>${esc(ch.label)}</b></a></li>`)
    .join('');

  const host = document.querySelector('[data-chapters]');
  host.innerHTML = chapters.map((ch) => chapterHTML(ch, H)).join('');

  return {
    hero: document.querySelector('.hero'),
    outro: document.querySelector('.outro'),
    start: document.querySelector('[data-start]'),
    navLinks: [...document.querySelectorAll('[data-nav]')],
    chapters: chapters.map((ch) => {
      const el = document.getElementById(ch.id);
      return {
        data: ch,
        el,
        lead: el.querySelector('.station__lead'),
        track: el.querySelector('.station__track'),
        items: [...el.querySelectorAll('.item')],
        count: el.querySelector('[data-count]'),
        dots: [...el.querySelectorAll('.dot')],
        prev: el.querySelector('[data-step="-1"]'),
        next: el.querySelector('[data-step="1"]'),
      };
    }),
  };
}

function chapterHTML(ch, H) {
  const n = ch.items.length;
  const pairs = Math.max(1, Math.ceil(n / 2));
  const height = (ch.station.y * H).toFixed(2);
  return `
<section class="station" id="${ch.id}" data-index="${ch.index}" data-station="${ch.station.key}" data-reveal="${ch.reveal}" aria-labelledby="${ch.id}-title" tabindex="-1">
  <div class="station__lead" aria-hidden="true">
    <div class="station__marker">
      <span class="station__marker-num"><b>${ch.num}</b>${esc(ch.label)}</span>
      <span class="station__marker-title">${splitLetters(ch.title)}</span>
    </div>
  </div>
  <div class="station__track" style="--pairs:${pairs};--items:${Math.max(1, n)}">
    <div class="station__frame">
      <header class="station__head">
        <p class="station__kicker"><b>${ch.num}</b><span>${esc(ch.label)}</span><span class="station__at">${esc(ch.station.label || ch.station.key)} · ${height} m</span></p>
        <h2 class="station__title" id="${ch.id}-title">${esc(ch.title)}</h2>
        ${ch.intro ? `<p class="station__intro">${esc(ch.intro)}</p>` : ''}
      </header>
      ${n ? `<div class="station__nav">
        <span class="station__count" aria-hidden="true"><b data-count>01</b> / ${pad(n)}</span>
        <button type="button" class="station__step" data-step="-1" aria-label="Previous ${esc(ch.label)}"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5"/></svg></button>
        <div class="dots">${ch.items.map((it, j) => `<button type="button" class="dot" data-goto="${j}" aria-label="${esc(it.title)}"></button>`).join('')}</div>
        <button type="button" class="station__step" data-step="1" aria-label="Next ${esc(ch.label)}"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m6 3 5 5-5 5"/></svg></button>
      </div>` : ''}
      <ol class="station__items">
        ${ch.items.map((it, j) => itemHTML(ch, it, j)).join('')}
      </ol>
    </div>
  </div>
</section>`;
}

function itemHTML(ch, it, j) {
  const id = `${ch.id}-${j + 1}`;
  const side = j % 2 === 0 ? 'left' : 'right';
  return `
<li class="item" data-item="${j}" data-side="${side}" style="--k:${j % 2}">
  <article class="card" aria-labelledby="${id}">
    ${it.image ? `<figure class="card__media"><img src="${esc(asset(it.image))}" alt="${esc(it.alt)}" loading="lazy" decoding="async"></figure>` : ''}
    <div class="card__body">
      <p class="card__meta"><span class="card__index">${pad(j + 1)}</span>${it.meta ? `<span>${esc(it.meta)}</span>` : ''}</p>
      <h3 class="card__title" id="${id}">${esc(it.title)}</h3>
      ${it.description ? `<p class="card__text">${esc(it.description)}</p>` : ''}
      ${it.tags.length ? `<ul class="tags">${it.tags.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>` : ''}
      ${it.links.length ? `<p class="card__links">${it.links.map(linkHTML()).join('')}</p>` : ''}
    </div>
  </article>
</li>`;
}

const linkHTML = (cls = '') => (l) => {
  const url = safeUrl(l.url);
  const external = /^https?:/i.test(url);
  return `<a${cls ? ` class="${cls}"` : ''} href="${esc(url)}"${external ? ' target="_blank" rel="noopener"' : ''}>${esc(l.label || url)}${external ? ' <span aria-hidden="true">↗</span>' : ''}</a>`;
};

// Words stay unbroken; each letter gets an index for the staggered reveal.
function splitLetters(text) {
  let i = 0;
  return String(text).split(' ').map((word) =>
    `<span class="w">${[...word].map((c) => `<span class="ch" style="--i:${i++}">${esc(c)}</span>`).join('')}</span>`,
  ).join(' ');
}

const slug = (s) => String(s).toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'section';
