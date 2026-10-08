// DOM side of the experience: active section and item, navigation, keyboard focus, progress,
// lead-in title reveals, and the ?debug HUD.
import { clamp, pad } from './util.js';

export function createUI({ dom, director, scroller, env, getMode }) {
  const root = document.documentElement;
  const progressBar = document.querySelector('.topbar__progress i');
  const heroName = document.querySelector('.backdrop__name');
  let shownProgress = '', shownHero = '';
  const hud = env.debug ? document.querySelector('.hud') : null;
  if (hud) hud.hidden = false;

  const shown = dom.chapters.map(() => -2);
  let shownChapter = -2;

  // Section links in the top bar
  dom.navLinks.forEach((a, i) => a.addEventListener('click', (e) => {
    e.preventDefault();
    scroller.scrollTo(director.chapterY(i), { duration: 1.8 });
    history.replaceState(null, '', `#${dom.chapters[i].data.id}`);
  }));
  document.querySelector('.topbar__brand')?.addEventListener('click', (e) => {
    e.preventDefault();
    scroller.scrollTo(0, { duration: 1.8 });
    history.replaceState(null, '', location.pathname + location.search);
  });

  // Item navigation inside a section: table of contents, dots, previous / next
  dom.chapters.forEach((ch, i) => {
    ch.el.addEventListener('click', (e) => {
      const goto = e.target.closest('[data-goto]');
      const step = e.target.closest('[data-step]');
      if (!goto && !step) return;
      const n = ch.items.length - 1;
      const current = director.state.items[i];
      const j = goto ? +goto.dataset.goto : clamp(current + +step.dataset.step, -1, n - 1);
      scroller.scrollTo(director.beatY(i, j), { duration: 1 });
    });

    // Keyboard: tabbing into a card that isn't on screen scrolls to its beat.
    ch.el.addEventListener('focusin', (e) => {
      if (getMode() !== 'cinematic') return;
      const li = e.target.closest('.item');
      if (!li) return;
      const j = +li.dataset.item;
      if (director.state.chapter !== i || director.state.items[i] !== j) {
        scroller.scrollTo(j < 0 ? director.chapterY(i) : director.beatY(i, j), { immediate: true });
      }
    });
  });

  // Big lead-in titles assemble letter by letter as they enter the viewport.
  const io = new IntersectionObserver((entries) => {
    entries.forEach((en) => en.target.classList.toggle('is-inview', en.isIntersecting));
  }, { rootMargin: '-15% 0px -15% 0px' });
  dom.chapters.forEach((ch) => io.observe(ch.lead));

  function update(state, extra = {}) {
    // Write styles only to the element that needs them, and only on change.
    const p = state.progress.toFixed(4);
    if (p !== shownProgress) { shownProgress = p; progressBar.style.transform = `scaleX(${p})`; }
    const h = clamp(1 - state.y / (director.vh * 0.9)).toFixed(3);
    if (h !== shownHero) { shownHero = h; heroName.style.opacity = h; }

    const cinematic = getMode() === 'cinematic';
    dom.chapters.forEach((ch, i) => {
      const item = cinematic ? state.items[i] : -1;
      if (item === shown[i]) return;
      shown[i] = item;
      ch.items.forEach((li, k) => li.classList.toggle('is-active', !cinematic || k === item + 1));
      ch.dots.forEach((d, k) => d.setAttribute('aria-current', k === item ? 'true' : 'false'));
      if (ch.count) ch.count.textContent = pad(item + 1);
      if (ch.prev) ch.prev.disabled = item < 0;
      if (ch.next) ch.next.disabled = item >= ch.items.length - 2;
    });

    if (state.chapter !== shownChapter) {
      shownChapter = state.chapter;
      dom.navLinks.forEach((a, i) => a.setAttribute('aria-current', i === state.chapter ? 'true' : 'false'));
      root.dataset.chapter = state.chapter;
    }

    if (hud) {
      const info = extra.info ?? {};
      hud.textContent = [
        `mode ${getMode()}  quality ${env.quality}  dpr ${info.dpr ?? '-'}  fps ${info.fps ?? '-'}`,
        `y ${Math.round(state.y)} / ${Math.round(director.maxScroll)}  ${state.segment} ${state.travel.toFixed(2)}`,
        `chapter ${state.chapter}  item ${state.chapter >= 0 && state.chapter < dom.chapters.length ? state.items[state.chapter] : '-'}  rot ${state.pose.rot.toFixed(2)}`,
        `draw calls ${info.calls ?? '-'}  tris ${info.tris ?? '-'}`,
      ].join('\n');
    }
  }

  // Force a full refresh (after a mode switch).
  function reset() { shown.fill(-2); shownChapter = -2; }

  return { update, reset };
}
