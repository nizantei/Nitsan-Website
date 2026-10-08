// Loads data/content.json and renders the sections. Adding a work = adding an object to a
// chapter's `items` array (and dropping its image into /work/media/). Adding a chapter = adding
// an object to `chapters`; `reveal` picks its 3D effect (orbit | stage | constellation | medals).
import { asset, esc, pad, safeUrl } from './util.js';

const REVEALS = ['orbit', 'stage', 'constellation', 'medals'];

export async function loadContent() {
  const res = await fetch(asset('data/content.json'), { cache: 'no-cache' });
  if (!res.ok) throw new Error(`content.json: HTTP ${res.status}`);
  return res.json();
}

export function normalize(data) {
  const chapters = (data.chapters ?? []).map((ch, i) => {
    const id = slug(ch.id || ch.label || ch.title || `section-${i + 1}`);
    return {
      id,
      index: i,
      num: pad(i + 1),
      label: ch.label || ch.title || id,
      title: ch.title || ch.label || id,
      intro: ch.intro || '',
      reveal: REVEALS.includes(ch.reveal) ? ch.reveal : 'orbit',
      side: ch.side === 'left' || ch.side === 'right' ? ch.side : i % 2 === 0 ? 'left' : 'right',
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

export function renderContent(content) {
  const { meta, chapters } = content;

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
  host.innerHTML = chapters.map(chapterHTML).join('');

  return {
    hero: document.querySelector('.hero'),
    outro: document.querySelector('.outro'),
    navLinks: [...document.querySelectorAll('[data-nav]')],
    chapters: chapters.map((ch) => {
      const el = document.getElementById(ch.id);
      return {
        data: ch,
        el,
        lead: el.querySelector('.chapter__lead'),
        track: el.querySelector('.chapter__track'),
        items: [...el.querySelectorAll('.item')], // [0] is the intro card, then one per work
        count: el.querySelector('[data-count]'),
        dots: [...el.querySelectorAll('.dot')],
        prev: el.querySelector('[data-step="-1"]'),
        next: el.querySelector('[data-step="1"]'),
      };
    }),
  };
}

function chapterHTML(ch) {
  const n = ch.items.length;
  return `
<section class="chapter" id="${ch.id}" data-index="${ch.index}" data-side="${ch.side}" data-reveal="${ch.reveal}" aria-labelledby="${ch.id}-title">
  <div class="chapter__lead">
    <p class="chapter__num">${ch.num} / ${esc(ch.label)}</p>
    <h2 class="chapter__title" id="${ch.id}-title" aria-label="${esc(ch.title)}">${splitLetters(ch.title)}</h2>
  </div>
  <div class="chapter__track" style="--beats:${n + 1}">
    <div class="chapter__frame">
      <div class="panel">
        <div class="panel__bar">
          <span class="panel__kicker"><b>${ch.num}</b> ${esc(ch.label)}</span>
          <span class="panel__count" aria-hidden="true"><b data-count>00</b> / ${pad(n)}</span>
        </div>
        <ol class="items">
          <li class="item item--intro is-active" data-item="-1">
            <div class="card card--intro">
              <p class="card__intro">${esc(ch.intro)}</p>
              ${n ? `<ul class="toc">${ch.items.map((it, j) => `<li><button type="button" class="toc__btn" data-goto="${j}"><span>${pad(j + 1)}</span>${esc(it.title)}</button></li>`).join('')}</ul>` : ''}
            </div>
          </li>
          ${ch.items.map((it, j) => itemHTML(ch, it, j)).join('')}
        </ol>
        ${n ? `<div class="item-nav">
          <button type="button" class="item-nav__step" data-step="-1" aria-label="Previous ${esc(ch.label)} item">←</button>
          <div class="dots">${ch.items.map((it, j) => `<button type="button" class="dot" data-goto="${j}" aria-label="${esc(it.title)}"></button>`).join('')}</div>
          <button type="button" class="item-nav__step" data-step="1" aria-label="Next ${esc(ch.label)} item">→</button>
        </div>` : ''}
      </div>
    </div>
  </div>
</section>`;
}

function itemHTML(ch, it, j) {
  const id = `${ch.id}-${j + 1}`;
  return `
<li class="item" data-item="${j}">
  <article class="card" aria-labelledby="${id}">
    ${it.image ? `<figure class="card__media"><img src="${esc(asset(it.image))}" alt="${esc(it.alt)}" loading="lazy" decoding="async"></figure>` : ''}
    <div class="card__body">
      ${it.meta ? `<p class="card__meta">${esc(it.meta)}</p>` : ''}
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
    `<span class="w" aria-hidden="true">${[...word].map((c) => `<span class="ch" style="--i:${i++}">${esc(c)}</span>`).join('')}</span>`,
  ).join(' ');
}

const slug = (s) => String(s).toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'section';
