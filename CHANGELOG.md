# Changelog

All notable changes to static-web-platform. Versions follow semantic versioning:
a breaking change to the public API (`src/index.ts`), the page contract or the
app build contract is a major version.

## 1.3.0 — 2026-10-05

From the first app migrations. No change needed in existing apps; some rules
become less strict, so apps can drop their workarounds.

Added
- `site.json` `"modes"`: only the declared `core/<mode>/` folders are isolated from
  each other; other `core/` sub-folders are plain organisation and import freely
  (previously every sub-folder was a "mode").
- `core/` may use `TextEncoder`, `TextDecoder`, `structuredClone` and `crypto`
  (`getRandomValues`, `randomUUID`, `subtle.digest`): available in pages, workers and
  Node (`tools/swp_tools/core-runtime.d.ts`). The DOM, `fetch` and storage stay
  forbidden.
- Images and fonts referenced from CSS (e.g. a library stylesheet) are embedded as
  `data:` URLs; CSP `font-src data:`. The build reports `app.js` / `app.css` sizes.
- Scenario step `{"upload": [selector, "tests/fixtures/…"]}` (synthetic fixtures only).
- Config mode `"dev"` (`swp build --dev`): no service worker, no install/download.

Changed
- Exact Node pin required in `mise.toml` (e.g. `"24.21.0"`), checked by `swp build`
  (npm versions differ in how they link binaries).
- Tap targets: a field's own visible `<label>` is part of its target. The
  platform's dialog checkboxes are back to normal size, in 44px label rows.
- `swp serve`: backlog 128 connections (was Python's default 5).

Fixed
- Keyboard walk tracks elements by identity: popovers opening or closing during the
  walk no longer confuse it.
- "Focus never hidden" (WCAG 2.4.11) is checked on desktop too; the skip link is
  above any sticky header.
- An unavailable consent answer in a scenario (e.g. `"once"` for a non-request
  origin) fails immediately with a clear message instead of a timeout.

## 1.2.0 — 2026-10-05

Added
- "Support the author" link: site.json `"support": {"url": "https://…"}` and
  `platform.supportLink()` (a plain link, never the provider's widget: nothing is
  loaded until clicked). The app places it; the gate fails when a declared link is
  not visible (site desktop, site phone, single file).

## 1.1.0 — 2026-10-04

Additive: existing apps keep working; new behaviour is opt-in through site.json,
except the stricter gate and the build checks listed under "Stricter".

Added
- Consent `"scope": "request"` per origin: asked every time, exact value shown
  (`net.fetch(url, init, { disclose })`), Deny / Send once, never remembered; the
  platform refuses such a request without `disclose`. Privacy lists it as "Asked
  every time".
- `"referrerPolicy"` per origin (`no-referrer` default, `origin`, `strict-origin`),
  applied to fetch/image and stated in the consent dialog.
- Share links: `platform.share.offer()` (warning listing the contents, copied only
  after confirmation, data after `#`) and `platform.share.incoming` (read once, removed
  from the address bar).
- Datasets in `src/data/` (+ `SOURCES.md`, 5 MB bundled budget) and optional
  `"assets"` (hosted site only; `platform.assets`).
- Web Workers (`"workers"`, `platform.worker(name)`), inlined in the single file and
  started from `blob:` (CSP `worker-src blob:` only when declared).
- Accessibility dialog: single-key shortcuts switch (`platform.shortcuts`, WCAG 2.1.4)
  and optional theme choice (`"themeSwitch"`); `base.css` honours
  `[data-theme]`.
- `data-swp-sticky`: scroll padding follows sticky headers (focus never hidden,
  WCAG 2.4.11).
- `"typecheck": {"command"}` (svelte-check, vue-tsc), `appBuild.inputs`, and
  `swp build --dev`.
- Verified: Svelte 5 + Vite 8 (example configuration in the README).

Stricter
- Build: layer rules enforced (`arch.py`), `core/` type-checked without the DOM,
  `netOrigins` validated, datasets need sources.
- Gate: app scenarios (`scenarios.json`, required), keyboard walk (reachable, visible
  focus, no trap, not hidden under sticky headers), no data in the URL / title, text
  spacing, single keys inert when shortcuts are off, forced colours, label-in-name,
  inputs ≥ 44px tall on phones.

Fixed
- Inlining hazard: `<!--` + `<script` inside an inlined script (Svelte runtime) could
  truncate the single file; now escaped and verified.
- The version fingerprint now includes build configuration (`*.config.*`,
  `appBuild.inputs`).

Changed
- TypeScript peer range widened to `>=6 <8`; esbuild peer optional.

## 1.0.0 — 2026-10-03

First release, extracted from the `static-web-app` skill.

- Runtime in layers: `core/` (pure), `services/` (consent, network, storage, update,
  install, offline), `ui/` (dialogs, action bar, `base.css`), `startPlatform()`.
- Feature registry (`createRegistry`): one renderer per content type, for apps
  organised as `core/` + `features/` + `main.ts`.
- `swp` command: `build` (tsc type check + esbuild or the app's own bundler +
  assembly), `check`, `verify`, `gate` (now with mobile checks: zoom allowed, form
  fields ≥ 16px, tap targets ≥ 44×44px, landscape reflow), `serve`, `icons`.
- Bundles keep `node_modules/…` paths (`--preserve-symlinks`): no local path in
  published files, identical output on every machine.
