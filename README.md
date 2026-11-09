# static-web-platform

The shared base of every static web app built with the `static-web-app` skill. Each
app keeps its own content, features and (optionally) framework. The platform provides
everything that must behave the same everywhere:

- **Local-only by default:** no request to another server without the user's consent
  (accessible dialog; "ask every time" with the exact value for user input;
  decisions revocable in *Privacy*), with a generated Content-Security-Policy as the
  hard ceiling.
- **One source, several outputs:** an installable app (PWA, offline, updates itself);
  a local copy chosen per app — a single-file HTML download, or a zip with a local
  server for apps that need a real origin, or none — that can check for updates
  (after consent); and, for apps that compute something, a command-line version that
  is also the app's library, sharing the page's code (runs with Deno, no network).
- **Accessibility built in:** dialogs, a single-key shortcut switch (WCAG 2.1.4), a
  theme choice, focus kept visible under sticky headers, and phone rules (16px fields,
  44px targets).
- **No data in the address bar:** shared links only through a warned, explicit
  *Share* action.
- **The `swp` command:** build (architecture check, type check, bundle, assembly),
  `check`, `verify` (byte-for-byte reproducibility), `gate` (security, consent,
  accessibility, keyboard, mobile, URL, local copy, command line, offline — on the
  first screen and on every app scenario), `serve`, `icons`.

## Architecture

```mermaid
flowchart LR
  subgraph platform["static-web-platform (this repo)"]
    core["core/ — pure: types, i18n, registry, version"]
    services["services/ — consent, network, storage, share, shortcuts,<br/>display, assets, workers, update, install, offline"]
    ui["ui/ — dialogs, action bar, base.css"]
    entry["platform.ts — startPlatform()"]
    pcli["cli/ — startCli() (Deno)"]
    launcher["launcher/ — local server (Deno)"]
    core --> services --> ui --> entry
  end
  subgraph app["an app"]
    acore["core/ (+ data/) — pure domain"]
    api["api/ — operations (programmatic API)"]
    shared["ui/ · state/ — shared helpers"]
    features["features/ — one capability each"]
    main["main.ts — wiring"]
    cli["cli/ — command line"]
    acore --> api --> features --> main
    shared --> features
    api --> cli
  end
  entry --> main
  pcli --> cli
```

Dependencies point inward only. The platform never imports app code. Apps use only
the public entries (`src/index.ts` for the page, `src/cli/index.ts` for the command
line), and their own layer rules are enforced by `swp build`
(`tools/swp_tools/arch.py`): `api/` imports only `core/` and `api/`; `cli/` imports only
`api/`, `core/`, `cli/` and `"static-web-platform/cli"`; nothing imports `cli/`.

| Platform layer | May use | Must not |
|---|---|---|
| `core/` | nothing | the DOM, the network, storage |
| `services/` | `core/`, browser APIs | render UI (questions go through injected functions) |
| `ui/` | `core/`, `services/`, the DOM | contain decision logic |
| `platform.ts` | everything above | — |
| `cli/` | its own files; Deno file and stream APIs (`deno-io.d.ts`) | the DOM, the network, the page layers |
| `launcher/` | `cli/deno-io.d.ts` + `Deno.serve` (`deno-serve.d.ts`) | anything but serving `public/` on 127.0.0.1 |

## Using it in an app

Each app includes this repository as a **Git submodule** in `platform/`, pinned to a
release, and installs it through npm from that folder:

```bash
git submodule add https://github.com/<owner>/static-web-platform.git platform
git -C platform checkout v2.0.0
```
```jsonc
// package.json of the app
"dependencies": { "static-web-platform": "file:platform" },
"devDependencies": { "typescript": "7.0.2", "esbuild": "0.28.2", "@types/node": "24.19.1" }
```
Peer ranges: TypeScript `>=6 <8` (7 by default; 6 for Svelte apps, because
`svelte-check` 4.x supports TypeScript up to 6), and esbuild `0.28` (optional when the
app has its own bundler). In CI, `actions/checkout` needs `submodules: true`.

### Public API (`import … from "static-web-platform"`)

```ts
const platform = startPlatform<MyOptions>({ strings: { fr: { … } } });   // first, once
platform.site                       // SiteConfig: id, title, lang, mode ("site" | "single" | "local" | "dev"),
                                    //   distribution, download, cli, version, options…
platform.t("key", { n: 3 })         // UI strings (platform + app), missing key = error
platform.store / sessionStore       // prefixed storage, never throws
platform.net.fetch(url, init, { disclose })    // consent-gated; null when refused; redirects never followed
                                               //   (throws RedirectBlockedError — t("redirectBlocked"))
platform.net.image(img, url, fallback)         // consent-gated image
platform.consent.request(origin)    // before enabling a library that loads its own resources
platform.share.offer(payload, items)           // warned share link (copied, never in the address bar)
platform.share.incoming             // data of an opened share link (already removed from the URL)
platform.shortcuts.add({ key: "/", description, run })   // single-key shortcuts (user can turn off)
platform.assets.fetch("data/big.json")         // optional served files (site, local server); null in the single file
platform.worker("solver")           // Web Worker, same call in every output
platform.setStatus(text, notice?)   // announced status line
platform.supportLink()              // "☕ Buy me a coffee" link (site.json "support"), or null; the app places it
createRegistry<Spec, Out, Ctx>()    // one renderer per content type
el(tag, props, …children), byId(id)            // small DOM helpers
isLocalCopy(mode), servesFiles(mode)           // what a page mode can do
```

### Command-line entry (`import … from "static-web-platform/cli"`)

The only platform import an app's `src/cli/` may use. The app lists its commands, in
workflow order; each one calls one operation of `src/api/`:

```ts
import { startCli } from "static-web-platform/cli";
import { analyse } from "../api/index.ts";
export * from "../api/index.ts";        // the same file is the app's library

startCli({ name: "tool", summary: "What the tool does", commands: [{
  name: "analyse", summary: "Analyse a file", input: "file",          // "file" (path or -) | "none"
  options: [{ name: "depth", description: "…", type: "number", default: 1 }],
  run: (bytes, options) => analyse(bytes ?? new Uint8Array(), options), // → { ok, value } | { ok: false, code, message }
  text: value => "…\n",                                                 // optional --format text
}] });
```
The frame gives every CLI the same grammar: `--help` (per command too), `--version`,
`FILE` or `-` (standard input), `--format json|text` (JSON by default), `--out FILE`
(`--force` to replace), and exit codes `0` success, `1` invalid input, `2` usage error,
`3` internal error. `runCli(spec, args, build, io)` is the same logic with injected
I/O, for unit tests.

### Page contract (`src/index.html`)
`<!-- BUILD:HEAD -->`, `<!-- BUILD:BODY -->`, an element `#app-actions` (the platform
adds Install / Download / Command line / Check for updates / Privacy / Accessibility /
status; ids `#install`, `#download`, `#download-cli`, `#check-update`, `#privacy`,
`#accessibility`, `#status`),
`<html lang>`, a skip link, and `data-swp-sticky` on any sticky header (the platform
keeps focused elements visible below it).

### `src/site.json`
| Key | Meaning |
|---|---|
| `id`, `title`, `shortName`, `lang`, `themeColor` | identity (storage prefix, manifest, `<title>`) |
| `siteUrl` | production URL ("" until known: local copies offer no update check) |
| `distribution` | the local copy: `"single"` (default, the single HTML file), `"local-server"` (`<id>-local.zip`: the page + a Deno launcher on 127.0.0.1, for apps that need a real origin; each app has its own default port in 29170–29998, a block the IANA registry leaves unassigned), `"site-only"` (none) |
| `downloadName` | file name of the single-file download (required with `"single"`) |
| `cli` | `{ "entry": "src/cli/main.ts" }`: command-line version, published as `<id>-cli.js` |
| `entry` | bundler entry (default `src/main.ts`) |
| `linkCheck` | `{ "sources": ["src/content.ts"], "output": "data/link-status.json" }`: links checked by `swp links` (status file read by a `core/` loader) |
| `netOriginsFrom` | `[{ "data": "data/rdap-dns.json", "directive": "connect-src", "purpose": "…", "scope": "request" }]`: every https origin listed in that dataset, declared exactly (one group in *Privacy*) |
| `netOrigins` | external servers: `{ "https://host": { "directive": "img-src", "purpose": "…", "scope": "origin"\|"request", "referrerPolicy": "no-referrer"\|"origin"\|"strict-origin" } }` |
| `options` | the app's own options (typed by the app) |
| `modes` | `["identifiers", "files"]`: `core/` sub-folders isolated from each other (other sub-folders import freely) |
| `themeSwitch` | offer a light / dark / system choice in *Accessibility* |
| `support` | `{ "url": "https://buymeacoffee.com/…" }`: "support the author" link, placed by the app with `platform.supportLink()` |
| `assets`, `precacheAssets` | optional files served next to the page, never in the single file (globs relative to `src/`); cached offline only if `true` |
| `workers` | `{ "name": "src/workers/name.ts" }` |
| `appBuild` | `{ "command": [...], "outDir": "build/app", "inputs": ["vite.config.ts"] }`: own bundler |
| `typecheck` | `{ "command": [...] }`: replaces `tsc` (e.g. `svelte-check`) |

### The app build contract (framework freedom)
`swp build` needs, in one folder:
- `app.js`: **one self-contained script** (all imports bundled, platform included),
  IIFE;
- `app.css`: optional;
- `workers/<name>.js`: one self-contained script per declared worker.

The command line (`cli.entry`) and the local-server launcher are always bundled by
esbuild as ES modules for Deno, whatever builds `app.js`.

By default esbuild produces them from `entry` and `workers`. TypeScript, JSX (React,
Preact) and CSS imports work out of the box; images and fonts referenced from CSS
(e.g. a library stylesheet such as `leaflet.css`) are embedded as `data:` URLs, so
they also work in the single file. With your own bundler, inline them too (Vite:
`build.assetsInlineLimit`). Frameworks that need `eval` at run time
are not allowed (the CSP forbids it).

**Verified frameworks** (full gate, byte-for-byte rebuild):
- none (plain TypeScript);
- Preact 11 (esbuild);
- **Svelte 5 + Vite 8**, with TypeScript 6 and `svelte-check` 4.7.6 as the type check:

```ts
// vite.config.ts (Svelte) — honours the contract; listed in appBuild.inputs
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";
export default defineConfig({
  plugins: [svelte()],
  resolve: { preserveSymlinks: true },     // node_modules/... paths, no local path in output
  build: {
    outDir: process.env.SWP_OUT_DIR ?? "build/app", emptyOutDir: true,
    minify: false, sourcemap: false, cssCodeSplit: false,   // readable, auditable
    lib: { entry: "src/main.ts", formats: ["iife"], name: "app", fileName: () => "app.js", cssFileName: "app" },
  },
});
```
```jsonc
// site.json
"appBuild": { "command": ["node_modules/.bin/vite", "build"], "outDir": "build/app",
              "inputs": ["vite.config.ts", "svelte.config.js"] },
"typecheck": { "command": ["node_modules/.bin/svelte-check", "--tsconfig", "./tsconfig.json", "--fail-on-warnings"] }
```
Vue is not verified yet.

**Dev servers:** `npx swp build --dev` writes `config.js` (mode `"dev"`: no service
worker, no install/download) and `base.css` into `build/dev/`. Serve that folder as static files (e.g. Vite `publicDir`) and load both
from the dev page, before the app.

### TypeScript requirements
`tsconfig.json`: `strict`, `moduleResolution: "bundler"`, `allowImportingTsExtensions`
(imports end in `.ts`), `verbatimModuleSyntax`, `erasableSyntaxOnly`, and
`resolveJsonModule` (datasets). These rules let Node's test runner execute the
TypeScript directly (`node --test`): no `enum`, no `namespace`, no constructor
parameter properties, and type-only imports written `import type`.

`src/core/` and `src/api/` are type-checked a second time **without the DOM
library**; besides ECMAScript they may use only `TextEncoder`, `TextDecoder`,
`structuredClone` and `crypto` (`getRandomValues`, `randomUUID`, `subtle.digest`) —
the APIs pages, workers, Node and Deno share (`tools/swp_tools/core-runtime.d.ts`).
`src/cli/` is checked the same way, plus only the Deno file and stream APIs
(`src/cli/deno-io.d.ts`): no `fetch`, no sockets, so network code fails the build.
Deno is the second barrier: the CLI runs without `--allow-net`.

**Node and Deno:** `mise.toml` pins exact versions (`node = "24.21.0"`, and
`deno = "2.9.8"` for apps with a command line or the local-server copy, which the gate
runs). `swp build` refuses another Node, because npm versions differ in how they link
package binaries. Users of the command line need Deno 2.9 (LTS) only:
`deno run --no-config --no-prompt --allow-read <id>-cli.js <command> FILE`.

## Commands

From the app's root, with Node on PATH (`mise exec -- …`):

| Command | Does |
|---|---|
| `npx swp build` | architecture check, type check (+ `core/`, `api/`, `cli/` purity), bundle, assemble `public/` |
| `npx swp build --dev` | only `config.js` + `base.css` for a dev server |
| `npx swp check` | `public/` is up to date with `src/` (no Node needed) |
| `npx swp verify` | `public/` is byte-for-byte a fresh rebuild |
| `npx swp gate` | the full verification gate (needs `scenarios.json`) |
| `npx swp serve` | serve `public/` with its `_headers`, imitating Cloudflare's "pretty URLs" (`/x.html` → `/x`) |
| `npx swp icons` | render the PNG icons from `src/icons/icon.svg` |
| `npx swp links [--write] [--report FILE]` | check the app's outgoing links (site.json `linkCheck`); used by a weekly CI job |
| `npx swp cors URL…` | before declaring an endpoint: does it answer CORS for the site and the app's local copy (`Origin: null`, or `http://127.0.0.1:<port>`)? |

## Developing the platform

```bash
mise exec -- npm ci
mise exec -- npm run typecheck
mise exec -- npm test          # core, consent, share (Node test runner); build tools, arch (unittest)
```
End-to-end behaviour is checked in the apps' CI (`npx swp gate`). Before tagging, run
one app (and the Svelte example, if the build contract changed) through
`swp build` + `swp gate`.

### First release (one time)
1. Commit the release (`feat: …`).
2. `git tag -a vX.Y.Z` (never move a tag afterwards).
3. Create the GitHub repository `static-web-platform`; then
   `git remote add origin …`, then `git push -u origin main --tags`.
4. The repository is public: apps' CI fetches the submodule with `submodules: true`.

### Every release
Update `CHANGELOG.md`, then bump `version` in `package.json` (semantic versioning:
breaking API, page contract or build contract = major), commit, and tag `vX.Y.Z`.
Apps update through Dependabot (`gitsubmodule`) or by hand, then rebuild `public/`
and run the gate.

## Licence

Licensed under the [Apache License, Version 2.0](LICENSE). Copyright 2026 Ben0x0a (see
[NOTICE](NOTICE)).

Apps may use any licence of their own. Every app's `app.js` contains platform code, so
it keeps the notice: `src/index.ts` starts with a `/*! … */` legal comment that
bundlers preserve. Don't strip legal comments from app bundles.

## Development & AI use

Generative AI was used in this project mainly to assist during the coding phase. The
original ideas and the overall structure are the owner's.
