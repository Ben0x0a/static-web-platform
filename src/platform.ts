/*
  platform.ts — startPlatform(): wires the services and the UI together and
  hands the app a Platform object. Every app calls it exactly once, first.

  Defines : Platform, startPlatform().
  Used by : apps (via index.ts) — with or without a framework.
  Uses    : core/*, services/*, ui/*; window.__SWP_SITE__ (injected by the
            build: config.js on the site, inlined in the single file); the
            page's action slot (default #app-actions).

  Dependency direction: core ← services ← ui ← platform ← app. Nothing in
  the platform imports app code.
*/
import { createI18n, type I18n, type StringTable } from "./core/i18n.ts";
import { PLATFORM_STRINGS } from "./core/strings.ts";
import type { NetOrigin, SiteConfig } from "./core/types.ts";
import { createAssets, type Assets } from "./services/assets.ts";
import { createConsent, type Consent } from "./services/consent.ts";
import { applyStoredTheme, keepFocusVisibleUnderStickyHeaders } from "./services/display.ts";
import { createInstall } from "./services/install.ts";
import { createNetwork, type Network } from "./services/network.ts";
import { registerServiceWorker } from "./services/offline.ts";
import { shareLink, takeIncomingShare } from "./services/share.ts";
import { createShortcuts, type Shortcuts } from "./services/shortcuts.ts";
import { startWorker } from "./services/workers.ts";
import { createStore, type PrefixedStore } from "./services/storage.ts";
import { mountActions } from "./ui/actions.ts";
import { mountDialogs, type ShareItem } from "./ui/dialogs.ts";
import { byId } from "./ui/dom.ts";
import { createSupportLink } from "./ui/support.ts";

export interface Platform<O = Record<string, unknown>> {
  site: SiteConfig<O>;
  t(key: string, vars?: Record<string, string | number>): string;
  /** Persistent storage, prefixed with the app id. */
  store: PrefixedStore;
  /** Per-browser-session storage, prefixed with the app id. */
  sessionStore: PrefixedStore;
  /** The only way to contact another origin (consent-gated). */
  net: Network;
  consent: Consent;
  setStatus(content: string | Node, notice?: boolean): void;
  /** Single-key shortcuts, switchable off by the user (WCAG 2.1.4). Never handle single keys yourself. */
  shortcuts: Shortcuts;
  /** Optional files of the hosted site (null / unavailable in the single file). */
  assets: Assets;
  /**
   * A new "support the author" link (site.json "support"), or null when the app
   * has none. Place it where you want; it must stay visible (the gate checks).
   */
  supportLink(): HTMLAnchorElement | null;
  /** Start a Web Worker declared in site.json "workers" (works in both outputs). */
  worker(name: string): Worker;
  share: {
    /** Data from an opened share link (already removed from the address bar), unvalidated; null if none. */
    incoming: unknown | null;
    /** Offer a share link: privacy warning listing `items`, copy only after confirmation. */
    offer(payload: unknown, items: ShareItem[]): Promise<boolean>;
  };
}

export interface StartOptions {
  /** The app's UI strings, per language (merged over the platform's). */
  strings?: StringTable;
  /** Id of the element receiving the action bar (default "app-actions"). */
  actionsSlot?: string;
}

let started = false;

export function startPlatform<O = Record<string, unknown>>(options: StartOptions = {}): Platform<O> {
  // Invariant: one platform per page — a second start would duplicate the
  // dialogs and buttons and register the service worker twice.
  if (started) throw new Error("startPlatform() called twice");
  started = true;
  const site = (window as Window & { __SWP_SITE__?: SiteConfig<O> }).__SWP_SITE__;
  // Invariant: the build injects the config before the app script; without it
  // the page was not produced by the platform build (or scripts are misordered).
  if (!site) throw new Error("window.__SWP_SITE__ missing: page not built by the platform build");

  // First thing: take any shared data out of the address bar (it must never
  // stay in the URL, history or bookmarks).
  const incoming = takeIncomingShare();
  document.documentElement.lang = site.lang;
  const i18n = createI18n(site.lang, PLATFORM_STRINGS);
  if (options.strings) i18n.add(options.strings);
  const store = createStore(site.id, () => localStorage);
  const sessionStore = createStore(site.id, () => sessionStorage);

  // The single file may contact its own site (update check): declared here,
  // and allowed in that file's CSP connect-src by the build.
  const declared = (): Record<string, NetOrigin> => site.mode === "single" && site.siteUrl
    ? { ...site.netOrigins, [new URL(site.siteUrl).origin]: { directive: "connect-src", purpose: i18n.t("purposeUpdate") } }
    : { ...site.netOrigins };

  let consent: Consent | null = null;
  applyStoredTheme(store);
  const shortcuts = createShortcuts(store);
  const dialogs = mountDialogs({ i18n, stores: [store, sessionStore], consent: () => consent as Consent,
    store, shortcuts, themeSwitch: site.themeSwitch });
  consent = createConsent({ local: store, session: sessionStore, lang: site.lang, declared, ask: dialogs.askConsent });
  const net = createNetwork(consent);
  const actions = mountActions({ slot: byId(options.actionsSlot ?? "app-actions"), site, i18n, dialogs,
    install: createInstall(), net, consent });
  if (site.mode === "site") registerServiceWorker();      // never in "dev" (the dev server has no sw.js)
  keepFocusVisibleUnderStickyHeaders();
  // Read-only hook for the verification gate (swp gate), which checks status
  // messages in the app's language. Exposes UI text only, nothing else.
  (window as Window & { __swpT?: I18n["t"] }).__swpT = i18n.t;

  // Share links point at the hosted site when known (the single file's own
  // file:// address is useless to someone else).
  const shareBase = site.mode === "single" && site.siteUrl ? site.siteUrl : location.href;
  const share = {
    incoming,
    offer: (payload: unknown, items: ShareItem[]) => dialogs.confirmShare(shareLink(shareBase, payload), items),
  };

  return { site, t: i18n.t, store, sessionStore, net, consent, setStatus: actions.setStatus, share,
           assets: createAssets(site), worker: name => startWorker(site, name), shortcuts,
           supportLink: () => (site.support ? createSupportLink(site.support.url, i18n) : null) };
}
