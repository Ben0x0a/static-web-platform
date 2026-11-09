/*
  core/types.ts — data shapes shared by the whole platform (pure: no DOM, no I/O).

  Defines : SiteConfig (what the build injects into every page), NetOrigin
            (a declared external server), VersionInfo (version.json),
            servesFiles() / isLocalCopy() (what a page mode can do).
  Used by : every other platform module and the apps (via index.ts).
  Uses    : nothing.
*/

/** CSP directives an external origin may be declared under. */
export type CspDirective = "img-src" | "connect-src" | "media-src" | "font-src" | "frame-src";

/** Referrer an external server may receive (default "no-referrer"). */
export type ReferrerChoice = "no-referrer" | "origin" | "strict-origin";

/**
 * "origin"  (default): one decision per server; may be remembered (session / always).
 * "request": the request carries user input (identifier, hash, search term,
 *            domain…): asked EVERY time, showing the exact value; never remembered.
 */
export type ConsentScope = "origin" | "request";

export interface NetOrigin {
  directive: CspDirective;
  /** Shown in the consent dialog: one text, or one per language. */
  purpose: string | Record<string, string>;
  scope?: ConsentScope;
  /** Some services require a referrer (e.g. OpenStreetMap tiles); stated in the dialog. */
  referrerPolicy?: ReferrerChoice;
  /** Set by the build for origins declared from a dataset (site.json "netOriginsFrom"). */
  group?: string;
}

/**
 * Injected by the build as `window.__SWP_SITE__` (config.js on the site,
 * inlined in the single file). `O` = the app's own options from site.json.
 */
export interface SiteConfig<O = Record<string, unknown>> {
  id: string;
  title: string;
  lang: string;
  /** Production URL ("" until known); local copies check it for updates. */
  siteUrl: string;
  /** What the local copy is (site.json "distribution"). */
  distribution: Distribution;
  /** File the Download link fetches (single file or zip); null when there is none. */
  download: string | null;
  /** File of the command-line version (Deno), null when the app has none. */
  cli: string | null;
  netOrigins: Record<string, NetOrigin>;
  options: O;
  mode: PageMode;
  /** Hash of the sources and toolchain, set by the build. */
  version: string;
  /** Build date, ISO 8601 (YYYY-MM-DD). */
  date: string;
  /** Optional files on the hosted site only (site.json "assets"), relative paths. */
  assets: string[];
  /** Declared Web Worker names (site.json "workers"). */
  workers: string[];
  /** Offer a light / dark / system choice in the Accessibility dialog (site.json "themeSwitch"). */
  themeSwitch: boolean;
  /** "Support the author" link (site.json "support"), null when the app has none. */
  support: { url: string } | null;
}

/** "single" file, "local-server" zip, or none ("site-only"). */
export type Distribution = "single" | "local-server" | "site-only";

/**
 * "site"   = the hosted app;
 * "single" = the downloaded single HTML file (file://);
 * "local"  = the local-server copy, served by its launcher on 127.0.0.1;
 * "dev"    = a framework dev server.
 */
export type PageMode = "site" | "single" | "local" | "dev";

/** The page's own files (workers, assets) are served next to it. */
export const servesFiles = (mode: PageMode): boolean => mode === "site" || mode === "local";

/** A copy taken away from the site: shows its version and checks the site for updates. */
export const isLocalCopy = (mode: PageMode): boolean => mode === "single" || mode === "local";

/** public/version.json, read by local copies to detect updates. */
export interface VersionInfo {
  version: string;
  date: string;
  /**
   * The local copy's file (single file or zip), relative to the site; "./" (the
   * site's home page) when the app has none, so older copies still get a valid link.
   */
  download: string;
  /** SHA-256 of that file; null when the app has no local copy. */
  sha256: string | null;
  /** The command-line bundle and its SHA-256, when the app has one. */
  cli: { file: string; sha256: string } | null;
}
