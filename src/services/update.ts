/*
  services/update.ts — update check of a local copy (single file or local server; no UI).

  Defines : checkForUpdate() → an UpdateResult the UI turns into a message.
  Used by : ui/actions.ts ("Check for updates" button, auto-check).
  Uses    : core/types.ts, core/version.ts, services/network.ts (consent-gated).
*/
import type { SiteConfig, VersionInfo } from "../core/types.ts";
import { isUpdateAvailable } from "../core/version.ts";
import type { Network } from "./network.ts";

export type UpdateResult =
  | { kind: "declined" }
  | { kind: "up-to-date" }
  /** `file`: the new copy of the same kind; null when the site no longer offers one (downloadUrl = the site). */
  | { kind: "available"; info: VersionInfo; downloadUrl: string; file: string | null }
  | { kind: "failed"; reason: string };

export async function checkForUpdate(site: SiteConfig<unknown>, net: Network): Promise<UpdateResult> {
  // HOW: after consent, read the site's small version.json and compare its
  // version (a hash of the sources) with this file's.
  try {
    const res = await net.fetch(new URL("version.json", site.siteUrl).href, { cache: "no-store" });
    if (!res) return { kind: "declined" };
    if (!res.ok) return { kind: "failed", reason: `HTTP ${res.status}` };
    const info = (await res.json()) as VersionInfo;
    if (!isUpdateAvailable(site.version, info)) return { kind: "up-to-date" };
    // A local-server copy is replaced by a new zip, a single file by a new single file.
    const file = (site.mode === "local" ? info.local?.file : info.download) ?? null;
    return { kind: "available", info, file, downloadUrl: new URL(file ?? "./", site.siteUrl).href };
  } catch (err) {
    // Offline, or the browser blocks file:// → https: the copy keeps working.
    return { kind: "failed", reason: (err as Error).message };
  }
}
