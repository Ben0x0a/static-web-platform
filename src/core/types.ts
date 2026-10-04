/*
  core/types.ts — data shapes shared by the whole platform (pure: no DOM, no I/O).

  Defines : SiteConfig (what the build injects into every page), NetOrigin
            (a declared external server), VersionInfo (version.json).
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
}

/**
 * Injected by the build as `window.__SWP_SITE__` (config.js on the site,
 * inlined in the single file). `O` = the app's own options from site.json.
 */
export interface SiteConfig<O = Record<string, unknown>> {
  id: string;
  title: string;
  lang: string;
  /** Production URL ("" until known); the single file checks it for updates. */
  siteUrl: string;
  downloadName: string;
  netOrigins: Record<string, NetOrigin>;
  options: O;
  /** "site" = hosted multi-file app; "single" = the downloadable file. */
  mode: "site" | "single";
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
}

/** public/version.json, read by single files to detect updates. */
export interface VersionInfo {
  version: string;
  date: string;
  download: string;
  sha256: string;
}
