# /work/: scroll-driven 3D portfolio page

A separate page next to the main site. Nothing in the main site links here yet, and the page is
`noindex` until launch (`<meta name="robots">` in `index.html`). The main site's files are untouched.

## Preview

```bash
# from the repo root
npx http-server . -p 8080 -c-1        # or: cd work/tools && npm install && npm run serve
# open http://localhost:8080/work/
```

On Vercel, every push to a branch gets a preview deployment; the page is at `<preview-url>/work/`.
Asset paths are absolute (`/work/...`), so `/work` and `/work/` both work.

Test switches (add to the URL):

| Switch | Effect |
|---|---|
| `?mode=static` | Reduced-motion layout (what users with "reduce motion" get) |
| `?mode=poster` | No-WebGL fallback: still image + static layout |
| `?quality=low` | Phone tier (fewer particles, lower resolution, no smooth scroll on touch) |
| `?debug` | HUD with mode, fps, scroll segment, active section and item |

## Add or change content

Everything is in **`data/content.json`**. Add an item by adding an object to a section's
`items`; drop its image in `media/`. The scroll length, item dots, counters and 3D objects
all adapt to the number of items.

```jsonc
{
  "title": "Required",
  "meta": "Year · platform · venue · issuer (optional)",
  "description": "Optional",
  "image": "media/my-app.webp",   // optional; webp/jpg/png/svg, ~1600px wide is plenty
  "alt": "Describe the image",
  "tags": ["Optional", "chips"],
  "links": [{ "label": "Live", "url": "https://..." }]
}
```

Sections (`chapters`) take `id`, `label`, `title`, `intro`, `items`, and:
- `reveal`: the 3D effect around the figure: `orbit` (ring of screens), `stage` (spotlight,
  slides, floor ripples), `constellation` (skill nodes with labels), `medals` (flipping badges).
- `side`: `left` or `right` for the text panel (alternates by default).

Name, tagline, email and outro links are under `meta`.

## Tune the choreography

- `js/config.js`: camera framing per section, turns per transition, snap behavior, particle
  formations, quality tiers, colors, model URL and height.
- `css/work.css`: `--lead` (scroll length of each transition) and `--beat` (scroll per item).

## Swap in the real model

1. Put the optimized GLB in `models/` and set `CONFIG.model.url` in `js/config.js`.
   Any glTF works: the page scales it to `CONFIG.model.height`, stands it on the floor,
   and layers the scan, dissolve and rim effects onto its own materials.
2. Regenerate the no-WebGL still: `cd tools && npm run serve` (one terminal), then `npm run poster`.

The photo-to-3D plan is in `tools/model/README.md`.

## How it works

```
index.html          layers: backdrop (giant name) → WebGL canvas → 3D labels → page content
css/work.css        layout, sticky section stops, compact (phone) layout, static/poster layouts
data/content.json   all content
js/main.js          boot: mode → content → 3D → measure → frame loop
js/env.js           mode and quality detection (+ URL switches)
js/content.js       renders sections from the JSON
js/director.js      scroll position → state (pose, active section and item, transition progress)
js/scroller.js      native scroll + Lenis smoothing on desktop
js/ui.js            active states, nav, keyboard focus, progress, debug HUD
js/scene/           Three.js: stage, figure effects, particles, floor, reveals, helpers
vendor/             pinned three.js + Lenis builds (see vendor/VERSIONS.txt)
tools/              dev scripts: vendoring, placeholder model, media, poster, screenshots
```

Scroll model: each section is a tall track with a sticky full-screen frame, so the page
"stops" on it while each beat of scrolling shows the next item. Between sections there is a
lead-in where the figure turns, scans and the particles re-form. Native scroll is the source of truth,
so keyboard, scrollbar, find-in-page and deep links (`/work/#talks`) keep working.

Fallbacks:
- **Reduced motion** (`prefers-reduced-motion`, followed live): content flows as a normal grid,
  the figure cuts between poses instead of animating, no smooth scroll, no particles motion.
- **No WebGL / 3D load failure**: same static layout over a still image (`media/poster.webp`).
  `three.js` is loaded on demand, so this path doesn't download it.
- **Phones**: figure up top with the panel as a bottom sheet, capped resolution, fewer
  particles, native touch scrolling; resolution steps down automatically if frames run slow.

## Tools

```bash
cd work/tools && npm install
npm run vendor        # rebuild vendor/ after changing three/lenis versions in package.json
npm run placeholder   # regenerate models/placeholder-figure.glb
npm run media         # regenerate placeholder images
npm run serve         # local server on :8080 (repo root)
npm run poster        # render media/poster.webp (needs the server)
npm run shots -- out  # screenshots of every mode + console errors (needs the server)
```

Headless runs need `CHROMIUM=/path/to/chrome` if Playwright's bundled browser isn't installed.
