/*
  services/assets.ts — optional files served next to the page, never inlined
  (site.json "assets": large datasets, heavy optional resources).

  Defines : createAssets() → { available, list, url, fetch }.
  Used by : platform.ts (platform.assets).
  Uses    : core/types.ts (SiteConfig, servesFiles).

  Site and local-server copy: same-origin fetch (no consent needed — it is
  the app's own server, or the launcher on 127.0.0.1).
  Single file: never fetched (the file must work offline and alone); the app
  shows t("assetSiteOnly") instead. The gate fails if the single file
  requests anything.
*/
import { servesFiles, type SiteConfig } from "../core/types.ts";

export interface Assets {
  /** True on the hosted site, false in the single-file download. */
  readonly available: boolean;
  /** Declared asset paths (relative to the site root). */
  list(): string[];
  /** URL of an asset served next to the page; null in the single file. */
  url(path: string): string | null;
  /** fetch() an asset served next to the page; null in the single file. */
  fetch(path: string): Promise<Response | null>;
}

export function createAssets(site: SiteConfig<unknown>): Assets {
  const available = servesFiles(site.mode);   // the local-server zip carries them too
  const check = (path: string): void => {
    // Invariant: only declared assets exist on the server; any other path is
    // a typo that would 404 in production.
    if (!site.assets.includes(path)) throw new Error(`Undeclared asset: ${path} (site.json "assets")`);
  };
  return {
    available,
    list: () => [...site.assets],
    url(path) { check(path); return available ? path : null; },
    async fetch(path) { check(path); return available ? fetch(path) : null; },
  };
}
