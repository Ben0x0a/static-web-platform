/*
  services/network.ts — the ONLY way for apps to reach another origin from their own code.

  Defines : createNetwork() → { fetch, image }, RedirectBlockedError.
  Used by : platform.ts (exposed to apps as platform.net), services/update.ts.
  Uses    : services/consent.ts; the browser's fetch (injectable for tests).

  Rules: same-origin requests (the site's own files) do not go through here;
  everything else does, after consent. Credentials are never sent; the
  referrer is the one declared for the origin (default: none).

  Redirects are NEVER followed (redirect: "manual"). A browser follows
  redirects by itself; the CSP only blocks UNDECLARED targets, so a redirect
  to another declared server would carry the value to a server the user did
  not approve. With "manual" the browser stops at the first answer: a
  redirect comes back as an opaque response (status 0, target unreadable —
  Fetch standard), the target is never contacted, and fetch() throws
  RedirectBlockedError so the app can explain it ("nothing was sent further").
  Images follow redirects with no way to stop them, so image() refuses
  origins declared "scope": "request" (user input goes through fetch()).
  Libraries that load their own resources cannot go through here: ask
  platform.consent.request(origin) before enabling them, and keep the origin
  declared so the CSP still limits them.
*/
import type { Consent, ConsentOptions } from "./consent.ts";

/** Thrown when an external server answered with a redirect: nothing was sent further. */
export class RedirectBlockedError extends Error {
  readonly origin: string;
  constructor(origin: string) {
    super(`${origin} answered with a redirect; it was not followed (nothing was sent further)`);
    this.name = "RedirectBlockedError";
    this.origin = origin;
  }
}

export interface Network {
  /**
   * fetch() after consent. Resolves null when the user refuses; throws
   * RedirectBlockedError when the server redirects (never followed).
   */
  fetch(url: string, init?: RequestInit, options?: ConsentOptions): Promise<Response | null>;
  /**
   * Point an <img> at another origin after consent; otherwise (or on error)
   * replace it with fallback(). Refuses "scope": "request" origins.
   */
  image(img: HTMLImageElement, url: string, fallback: () => Element, options?: ConsentOptions): Promise<void>;
}

export function createNetwork(consent: Consent, doFetch: typeof fetch = (...args) => fetch(...args)): Network {
  const referrerOf = (origin: string): ReferrerPolicy => consent.declared()[origin]?.referrerPolicy ?? "no-referrer";
  return {
    async fetch(url, init = {}, options = {}) {
      const origin = new URL(url).origin;
      if (!(await consent.request(origin, options))) return null;
      // credentials, referrer and redirect are fixed last: the app cannot loosen them.
      const response = await doFetch(url, { ...init, credentials: "omit", referrerPolicy: referrerOf(origin), redirect: "manual" });
      if (response.type === "opaqueredirect" || (response.status >= 300 && response.status < 400)) {
        throw new RedirectBlockedError(origin);
      }
      return response;
    },
    async image(img, url, fallback, options = {}) {
      try {
        const origin = new URL(url).origin;
        // Invariant: images follow redirects silently, so they may never carry
        // user input — request-scoped origins are for fetch() only.
        if (consent.declared()[origin]?.scope === "request") {
          throw new Error(`net.image() refuses ${origin}: declared "scope": "request" (use net.fetch with disclose)`);
        }
        if (await consent.request(origin, options)) {
          img.referrerPolicy = referrerOf(origin);
          img.onerror = () => img.replaceWith(fallback());
          img.src = url;
          return;
        }
      } catch (err) {
        console.error((err as Error).message);   // undeclared origin / misuse = bug: make the gate fail
      }
      img.replaceWith(fallback());
    },
  };
}
