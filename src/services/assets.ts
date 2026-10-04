/*
  services/assets.ts — optional files published on the hosted site only
  (site.json "assets": large datasets, heavy optional resources).

  Defines : createAssets() → { available, list, url, fetch }.
  Used by : platform.ts (platform.assets).
  Uses    : core/types.ts (SiteConfig).

  Site: same-origin fetch (no consent needed — it is the app's own server).
  Single file: never fetched (the file must work offline and alone); the app
  shows t("assetSiteOnly") instead. The gate fails if the single file
  requests anything.
*/
import type { SiteConfig } from "../core/types.ts";

export interface Assets {
  /** True on the hosted site, false in the single-file download. */
  readonly available: boolean;
  /** Declared asset paths (relative to the site root). */
  list(): string[];
  /** URL of an asset on the hosted site; null in the single file. */
  url(path: string): string | null;
  /** fetch() an asset on the hosted site; null in the single file. */
  fetch(path: string): Promise<Response | null>;
}

export function createAssets(site: SiteConfig<unknown>): Assets {
  const available = site.mode === "site";
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
