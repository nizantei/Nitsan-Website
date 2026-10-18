// DOM side of the experience: the works on screen at each station, navigation, keyboard focus,
// progress, the height rail, station titles during travel, and the ?debug HUD.
import { clamp, pad } from './util.js';

export function createUI({ dom, director, scroller, start, env, config, getMode }) {
  const root = document.documentElement;
  const H = config.model.height;
  const progressBar = document.querySelector('.topbar__progress i');
  const heroName = document.querySelector('.backdrop__name');
  const rail = document.querySelector('.rail');
  const railMark = rail?.querySelector('.rail__mark');
  const railValue = rail?.querySelector('[data-rail-value]');
  let shownProgress = '', shownHero = '', shownRail = '', shownValue = '';
  const hud = env.debug ? document.querySelector('.hud') : null;
  if (hud) hud.hidden = false;

  const shown = dom.chapters.map(() => '');
  const coming = dom.chapters.map(() => false);
  let shownChapter = -2;

  // Height rail: one tick per station, at its height on the body.
  if (rail) {
    rail.querySelector('.rail__ticks').innerHTML = dom.chapters.map((ch) =>
      `<li style="--h:${ch.data.station.y.toFixed(3)}"><span>${ch.data.num}</span></li>`).join('');
  }

  const travelTo = (y, from) => {
    start.release();
    // The zoom from the full figure gets the long, cinematic glide.
    scroller.scrollTo(y, { duration: from < 4 ? config.start.duration : 1.8 });
  };

  // Station links in the top bar
  dom.navLinks.forEach((a, i) => a.addEventListener('click', (e) => {
    e.preventDefault();
    travelTo(director.chapterY(i), scroller.y);
    history.replaceState(null, '', `#${dom.chapters[i].data.id}`);
  }));
  document.querySelector('.topbar__brand')?.addEventListener('click', (e) => {
    e.preventDefault();
    scroller.scrollTo(0, { duration: config.start.duration });
    history.replaceState(null, '', location.pathname + location.search);
  });

  // Navigation inside a station: dots, previous / next
  dom.chapters.forEach((ch, i) => {
    ch.el.addEventListener('click', (e) => {
      const goto = e.target.closest('[data-goto]');
      const step = e.target.closest('[data-step]');
      if (!goto && !step) return;
      const beats = director.stops[i + 1]?.beats ?? 1;
      const current = Math.max(0, director.state.beats[i]);
      const b = goto ? director.beatOf(+goto.dataset.goto) : clamp(current + +step.dataset.step, 0, beats - 1);
      scroller.scrollTo(director.beatY(i, b), { duration: 1 });
    });

    // Keyboard: tabbing into a card that isn't on screen scrolls to its beat.
    ch.el.addEventListener('focusin', (e) => {
      if (getMode() !== 'cinematic') return;
      const li = e.target.closest('.item');
      if (!li) return;
      const b = director.beatOf(+li.dataset.item);
      if (director.state.chapter !== i || director.state.beats[i] !== b) {
        start.release();
        scroller.scrollTo(director.beatY(i, b), { immediate: true });
      }
    });
  });

  function update(state, extra = {}) {
    // Write styles only to the element that needs them, and only on change.
    const p = state.progress.toFixed(4);
    if (p !== shownProgress) { shownProgress = p; progressBar.style.transform = `scaleX(${p})`; }
    const h = clamp(1 - state.intro * 1.6).toFixed(3);
    if (h !== shownHero) { shownHero = h; heroName.style.opacity = h; }

    const cinematic = getMode() === 'cinematic';
    const compact = director.compact;
    dom.chapters.forEach((ch, i) => {
      const beat = cinematic ? state.beats[i] : -1;
      const key = `${cinematic}${compact}${beat}`;
      if (key === shown[i]) return;
      shown[i] = key;
      const n = ch.items.length;
      const on = (j) => beat >= 0 && director.beatOf(j) === beat;
      ch.items.forEach((li, j) => li.classList.toggle('is-active', !cinematic || on(j)));
      ch.dots.forEach((d, j) => d.setAttribute('aria-current', on(j) ? 'true' : 'false'));
      ch.el.classList.toggle('is-here', cinematic && beat >= 0);
      if (ch.count) {
        const b = Math.max(0, beat);
        ch.count.textContent = compact || 2 * b + 1 >= n ? pad(compact ? b + 1 : 2 * b + 1) : `${pad(2 * b + 1)}–${pad(2 * b + 2)}`;
      }
      const beats = director.stops[i + 1]?.beats ?? 1;
      if (ch.prev) ch.prev.disabled = beat <= 0;
      if (ch.next) ch.next.disabled = beat >= beats - 1;
    });

    // While the camera travels to a station, its title assembles where the station's header will be.
    dom.chapters.forEach((ch, i) => {
      const on = cinematic && i > 0 && state.next === i && state.travel > 0.12 && state.beats[i] < 0;
      if (on !== coming[i]) { coming[i] = on; ch.el.classList.toggle('is-coming', on); }
    });

    if (state.chapter !== shownChapter) {
      shownChapter = state.chapter;
      dom.navLinks.forEach((a, i) => a.setAttribute('aria-current', i === state.chapter ? 'true' : 'false'));
      root.dataset.chapter = state.chapter;
    }

    // Height rail: where on the body the camera is looking, in meters.
    if (railMark) {
      const f = clamp(state.pose.lookY / H);
      const r = f.toFixed(4);
      if (r !== shownRail) { shownRail = r; railMark.style.setProperty('--h', r); }
      const v = `${state.pose.lookY.toFixed(2)} m`;
      if (v !== shownValue) { shownValue = v; railValue.textContent = v; }
      rail.classList.toggle('is-on', cinematic && state.intro > 0.6 && state.chapter < dom.chapters.length);
    }

    if (hud) {
      const info = extra.info ?? {};
      const ch = state.chapter;
      hud.textContent = [
        `mode ${getMode()}  quality ${env.quality}  dpr ${info.dpr ?? '-'}  fps ${info.fps ?? '-'}`,
        `y ${Math.round(state.y)} / ${Math.round(director.maxScroll)}  ${state.segment} ${state.travel.toFixed(2)}  intro ${state.intro.toFixed(2)}${start.gated ? '  gated' : ''}`,
        `station ${ch}  beat ${ch >= 0 && ch < dom.chapters.length ? state.beats[ch] : '-'}  look ${state.pose.lookY.toFixed(2)}  dist ${state.pose.dist.toFixed(2)}`,
        `draw calls ${info.calls ?? '-'}  tris ${info.tris ?? '-'}`,
      ].join('\n');
    }
  }

  // Force a full refresh (after a mode switch).
  function reset() { shown.fill(''); coming.fill(false); dom.chapters.forEach((ch) => ch.el.classList.remove('is-coming')); shownChapter = -2; }

  return { update, reset };
}
