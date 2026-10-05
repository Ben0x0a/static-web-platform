/*
  index.ts — public API of static-web-platform (what apps import).

  Defines : the re-exports below; nothing else is public.
  Used by : apps: `import { startPlatform, el } from "static-web-platform"`.
  Uses    : platform.ts, core/*, services/* (types), ui/dom.ts.
*/
export { startPlatform } from "./platform.ts";
export type { Platform, StartOptions } from "./platform.ts";
export type { SiteConfig, NetOrigin, VersionInfo, CspDirective, ConsentScope, ReferrerChoice } from "./core/types.ts";
export type { Consent, ConsentOptions } from "./services/consent.ts";
export type { StringTable } from "./core/i18n.ts";
export { createRegistry } from "./core/registry.ts";
export type { Registry } from "./core/registry.ts";
export type { PrefixedStore } from "./services/storage.ts";
export type { Network } from "./services/network.ts";
export { RedirectBlockedError } from "./services/network.ts";
export type { Assets } from "./services/assets.ts";
export type { Shortcut, Shortcuts } from "./services/shortcuts.ts";
export type { Theme } from "./services/display.ts";
export { el, byId } from "./ui/dom.ts";
export type { ShareItem } from "./ui/dialogs.ts";
export { encodeShare, decodeShare } from "./services/share.ts";
