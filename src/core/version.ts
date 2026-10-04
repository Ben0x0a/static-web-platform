/*
  core/version.ts — version and date helpers (pure).

  Defines : isUpdateAvailable(), displayDate(), shortVersion().
  Used by : services/update.ts, ui/actions.ts.
  Uses    : core/types.ts.
*/
import type { VersionInfo } from "./types.ts";

/** Versions are content hashes, not ordered numbers: any difference = update. */
export const isUpdateAvailable = (localVersion: string, online: VersionInfo): boolean =>
  online.version !== localVersion;

/** "2026-10-03" → "03.10.2026" (Swiss/European order). */
export const displayDate = (iso: string): string => iso.split("-").reverse().join(".");

export const shortVersion = (version: string): string => version.slice(0, 7);
