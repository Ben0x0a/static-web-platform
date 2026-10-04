/*
  services/share.ts — "share current elements" links (pure encoding + address-bar hygiene).

  Defines : encodeShare(), decodeShare(), shareLink(), takeIncomingShare(), SHARE_PREFIX.
  Used by : platform.ts (incoming share on start, platform.share.offer via ui/dialogs.ts).
  Uses    : browser location/history (takeIncomingShare only).

  Rules (static-web-app skill): the address bar never carries data. A share
  link is only created by an explicit Share action, after a warning listing
  what it contains, and is COPIED (never put in the address bar). Data goes in
  the fragment (#share=…), which browsers never send to a server. An incoming
  share is read once and removed from the address bar immediately.
*/

export const SHARE_PREFIX = "#share=";

/** JSON → UTF-8 → base64url (no padding): safe in a URL fragment. */
export function encodeShare(payload: unknown): string {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  let binary = "";
  bytes.forEach(b => { binary += String.fromCharCode(b); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** Inverse of encodeShare(); null for anything malformed (never throws on user input). */
export function decodeShare(encoded: string): unknown | null {
  try {
    const base64 = encoded.replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(base64 + "=".repeat((4 - (base64.length % 4)) % 4));
    const bytes = Uint8Array.from(binary, c => c.charCodeAt(0));
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)) as unknown;
  } catch {
    return null;
  }
}

/** Full link: base address (no query, no fragment) + #share=<payload>. */
export const shareLink = (base: string, payload: unknown): string =>
  `${base.split("#")[0]?.split("?")[0] ?? base}${SHARE_PREFIX}${encodeShare(payload)}`;

/**
 * Read an incoming share once, then clean the address bar (history.replaceState),
 * so the data is not kept in history, bookmarks or copied URLs. Returns the
 * decoded payload (unvalidated — the app must check its shape) or null.
 */
export function takeIncomingShare(): unknown | null {
  if (!location.hash.startsWith(SHARE_PREFIX)) return null;
  const payload = decodeShare(location.hash.slice(SHARE_PREFIX.length));
  history.replaceState(history.state, "", location.pathname + location.search);
  return payload;
}
