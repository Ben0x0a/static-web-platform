---
name: static-web-app
description: Build, convert, review or deploy a static web app (start page, browser-based viewer or utility, small tool) on static-web-platform, the shared base included as a Git submodule. Shipped as an installable, mobile-ready PWA plus a single-file HTML download. Enforces local-only operation with consent before any external request, no data in the URL, a generated CSP, WCAG 2.2 AA, mobile rules, enforced layer boundaries, reproducible builds and an automated verification gate (`swp gate`). Use when creating, structuring, reviewing or deploying such an app, or adding network access, datasets, workers, sharing, offline/install, mobile or accessibility work to one.
---

# Skill: Static Web App

Apps built on `static-web-platform` share one base for consent, network, storage,
sharing, shortcuts, install, download, update, build and verification. This skill
holds the **rules and the workflow**. The **platform README** (`platform/README.md` in
an app) is the reference for the public API, `site.json`, the page and build
contracts, and the `swp` commands: read it before writing code, and never duplicate
it here.

| File | Content |
|---|---|
| `assets/template/` | the starting app (copy it for a new app) |
| `assets/workflows/links.yml` | weekly link check, for apps that list links |
| `references/scenarios.md` | `scenarios.json`: screens reached by interaction, re-checked by the gate |
| `references/accessibility.md` | WCAG 2.2 AA checklist, patterns, manual pass |

## Scope
In scope: pages and tools whose logic runs in the browser and can be served as
static files. Out of scope: content sites made with a static site generator, and
server-side or multi-user deployments.

## Layers (enforced by `swp build`)
```
src/
  site.json   settings          core/      PURE domain logic + types, unit-tested
  index.html  page shell        data/      bundled datasets + SOURCES.md (read via core/)
  main.ts     wiring only       features/  one capability each, with its own CSS
  content.ts  typed content     ui/ state/ optional shared display helpers / shared state
                                workers/   optional Web Workers (core/ only)
```
- `core/` imports nothing but `core/`, `data/` and pure packages: no DOM, no
  `fetch`, no storage, no platform. Logic that can be pure goes here, with a test.
- A feature never imports another feature; features are combined in `main.ts` or
  through `createRegistry()`. Shared state goes in `state/`.
- The platform is imported only as `"static-web-platform"`, never by deep path.
- TypeScript: `strict`, imports with `.ts` extensions, `import type` for types, no
  `enum` / `namespace` / constructor parameter properties, JSON imported
  `with { type: "json" }`. Node pinned exactly in `mise.toml`.
- Any framework may render the app's elements (plain TS, Preact, Svelte verified) if
  its build honours the build contract in the README; no `eval` at run time.

## Rules
1. **Local-only by default.** Zero requests to other origins with default settings:
   no CDN, web font, analytics or icon service; third-party code is bundled.
   - Other origins only through `platform.net.fetch` / `platform.net.image`, declared
     in `site.json` `netOrigins` (the CSP is generated from them).
   - A request carrying user input is declared `"scope": "request"` and passes
     `{ disclose: value }`: the user sees the exact value and is asked every time.
   - Libraries that load their own resources are enabled only after
     `platform.consent.request(origin)`.
   - Redirects are never followed: call the final server directly.
   - Check endpoints with `swp cors` (the single file sends `Origin: null`).
2. **No data in the address bar** or the page title. Results are shared only through
   `platform.share.offer()`, which warns and copies the link; incoming share data is
   validated in `core/`.
3. **One source, reproducible outputs.** Edit `src/` only; `swp build` writes
   `public/` (hosted site + single file), which is committed. `swp verify` proves a
   byte-for-byte rebuild.
4. **Datasets** live in `src/data/`, each described in `SOURCES.md` (source, date,
   licence, SHA-256, update procedure), read through a typed `core/` loader with a
   test pinning count and hash; check the licence before bundling; 5 MB budget,
   larger files as site-only `assets`. The interface shows dataset name and date next
   to facts taken from it.
5. **Mobile:** zoom never blocked; fields ≥ 16px and ≥ 44px tall; tap targets
   ≥ 44×44px (visible box); no horizontal scroll at 320px; sticky headers carry
   `data-swp-sticky`.
6. **Accessibility (WCAG 2.2 AA):** landmarks, headings, real buttons, links and
   labels, status messages in `role="status"`, contrast in every theme, full keyboard
   use with visible focus, single-key shortcuts only through `platform.shortcuts`,
   a click alternative to every drag (`references/accessibility.md`).
7. **Sensitive input** (files with personal or case data) is processed in memory,
   never uploaded; show input hashes; every derived fact shows its origin (parsed,
   calculated, dataset, external); nothing persisted unless the user chooses.
8. **Content hygiene:** no personal data or internal paths in shipped content;
   unverifiable content marked `TODO`, never invented; links checked before release.
9. **Support link** (optional): `site.json` `support` + `platform.supportLink()`
   placed visibly; a plain link, never a provider widget.

## Workflow
**New app**
1. Copy `assets/template/`; set `id`, `title`, `shortName`, `lang`, `themeColor`,
   `downloadName` in `src/site.json` and `name` in `package.json`.
2. `git submodule add https://github.com/<owner>/static-web-platform.git platform`,
   then `git -C platform checkout v<release>`; `mise exec -- npm install`.
3. Write `src/core/` with tests, then `src/features/`, `src/content.ts`,
   `src/main.ts`; replace `src/icons/icon.svg` and run `npx swp icons`.
4. Add a scenario for every screen reached by interaction (`references/scenarios.md`).
5. Run the gate below, then the manual accessibility pass; fill in the README.

**Updating the platform in an app:** read `platform/CHANGELOG.md`, check out the new
tag in `platform/`, rebuild, run the gate, commit the pointer with `public/`.

## Verification (before reporting done)
```bash
mise exec -- npm run typecheck && mise exec -- npm test
mise exec -- npx swp build
mise exec -- npx swp verify
mise exec -- npx swp gate
```
The gate checks accessibility, keyboard, mobile rules, URL and title, requests
without consent, CSP, single file, offline and update, on the first screen and on
every scenario, on desktop and phone. Report explicitly what was **not** tested
(other browsers, real phones, real screen reader, voice control).

## CI
The template's `.github/workflows/ci.yml` runs install, typecheck, tests,
`swp check`, `swp verify` and `swp gate` on every push and pull request, with actions
pinned to commit SHAs and Dependabot for actions, npm and the submodule. CI never
deploys: the host publishes the committed `public/`.
