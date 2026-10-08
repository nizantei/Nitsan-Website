// Decides how the page runs on this device. URL overrides make every path testable on desktop:
//   ?mode=cinematic|static|poster   ?quality=high|low   ?debug

// Keep in sync with the compact @media query in css/work.css.
export const COMPACT_QUERY = '(max-width: 760px), (max-aspect-ratio: 4/5)';

export function detectEnv() {
  const params = new URLSearchParams(location.search);
  const reducedQuery = matchMedia('(prefers-reduced-motion: reduce)');
  const touch = matchMedia('(pointer: coarse)').matches;
  const compact = matchMedia(COMPACT_QUERY).matches;

  const forcedMode = ['cinematic', 'static', 'poster'].includes(params.get('mode')) ? params.get('mode') : null;
  const mode = forcedMode ?? (!hasWebGL2() ? 'poster' : reducedQuery.matches ? 'static' : 'cinematic');

  const cores = navigator.hardwareConcurrency || 8;
  const memory = navigator.deviceMemory || 8;
  const forcedQuality = ['high', 'low'].includes(params.get('quality')) ? params.get('quality') : null;
  const quality = forcedQuality ?? (touch || compact || cores <= 2 || memory <= 2 ? 'low' : 'high');

  return { mode, quality, touch, forcedMode, reducedQuery, debug: params.has('debug') };
}

export function applyModeClass(mode) {
  const root = document.documentElement;
  root.classList.remove('is-cinematic', 'is-static', 'is-poster');
  root.classList.add(`is-${mode}`);
}

function hasWebGL2() {
  try {
    return !!document.createElement('canvas').getContext('webgl2');
  } catch {
    return false;
  }
}
