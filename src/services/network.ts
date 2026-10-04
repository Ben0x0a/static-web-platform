/*
  services/network.ts — the ONLY way for apps to reach another origin from their own code.

  Defines : createNetwork() → { fetch, image }.
  Used by : platform.ts (exposed to apps as platform.net), services/update.ts.
  Uses    : services/consent.ts.

  Rules: same-origin requests (the site's own files) do not go through here;
  everything else does, after consent. Credentials are never sent; the
  referrer is the one declared for the origin (default: none).
  Libraries that load their own resources (map tiles, PDF.js…) cannot go
  through here: ask platform.consent.request(origin) before enabling them,
  and keep the origin declared so the CSP still limits them.
*/
import type { Consent, ConsentOptions } from "./consent.ts";

export interface Network {
  /** fetch() after consent. Resolves null when the user refuses. */
  fetch(url: string, init?: RequestInit, options?: ConsentOptions): Promise<Response | null>;
  /** Point an <img> at another origin after consent; otherwise (or on error) replace it with fallback(). */
  image(img: HTMLImageElement, url: string, fallback: () => Element, options?: ConsentOptions): Promise<void>;
}

export function createNetwork(consent: Consent): Network {
  const referrerOf = (origin: string): ReferrerPolicy => consent.declared()[origin]?.referrerPolicy ?? "no-referrer";
  return {
    async fetch(url, init = {}, options = {}) {
      const origin = new URL(url).origin;
      if (!(await consent.request(origin, options))) return null;
      return fetch(url, { ...init, credentials: "omit", referrerPolicy: referrerOf(origin) });
    },
    async image(img, url, fallback, options = {}) {
      try {
        const origin = new URL(url).origin;
        if (await consent.request(origin, options)) {
          img.referrerPolicy = referrerOf(origin);
          img.onerror = () => img.replaceWith(fallback());
          img.src = url;
          return;
        }
      } catch (err) {
        console.error((err as Error).message);   // undeclared origin / missing disclose = bug: make the gate fail
      }
      img.replaceWith(fallback());
    },
  };
}
