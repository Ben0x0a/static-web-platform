/*
  services/consent.ts — the consent gate's decision logic (no UI).

  Defines : createConsent() → { request, state, forget, declared }, ConsentQuestion.
  Used by : services/network.ts (every external request asks it first),
            ui/dialogs.ts (privacy dialog lists and forgets decisions), apps
            enabling a library that loads its own resources (request first).
  Uses    : core/types.ts, services/storage.ts; the question itself is asked
            through the injected `ask` function (ui/dialogs.ts in production,
            a stub in tests) — so the logic is testable without a browser.

  Scope "origin" (default): "always" lives in localStorage; "session"/"deny"
  in sessionStorage (a reload does not ask again; closing the browser
  forgets); parallel requests to one origin share a single prompt.
  Scope "request": every call asks, shows the exact value sent, offers only
  Deny / Send once, and never reads or writes a stored decision.
*/
import type { ConsentScope, NetOrigin, ReferrerChoice } from "../core/types.ts";
import type { PrefixedStore } from "./storage.ts";

export type ConsentAnswer = "deny" | "once" | "session" | "always";
export type ConsentState = "always" | "session-allow" | "session-deny" | "ask" | "per-request";

export interface ConsentOptions {
  /** The exact value this request sends (user input), shown verbatim. Required for scope "request". */
  disclose?: string;
}

export interface ConsentQuestion {
  origin: string;
  purpose: string;
  scope: ConsentScope;
  referrer: ReferrerChoice;
  disclose?: string;
}

export interface ConsentDeps {
  local: PrefixedStore;
  session: PrefixedStore;
  lang: string;
  /** Every origin the app may contact (site.json netOrigins + implicit ones). */
  declared: () => Record<string, NetOrigin>;
  /** Ask the user; resolves with their answer (Esc / close = "deny"). */
  ask: (question: ConsentQuestion) => Promise<ConsentAnswer>;
}

export interface Consent {
  request(origin: string, options?: ConsentOptions): Promise<boolean>;
  state(origin: string): ConsentState;
  forget(origin: string): void;
  declared(): Record<string, NetOrigin>;
}

export const purposeText = (purpose: NetOrigin["purpose"], lang: string): string =>
  typeof purpose === "string" ? purpose : (purpose[lang] ?? Object.values(purpose)[0] ?? "");

export function createConsent(deps: ConsentDeps): Consent {
  const key = (origin: string) => `consent:${origin}`;
  const pending = new Map<string, Promise<boolean>>();
  const definition = (origin: string): NetOrigin => {
    const def = deps.declared()[origin];
    // Invariant: code may only contact declared origins. An undeclared origin
    // is a bug — failing loudly keeps "nothing leaves without consent" auditable.
    if (!def) throw new Error(`Undeclared external origin: ${origin}`);
    return def;
  };

  const state = (origin: string): ConsentState => {
    if ((deps.declared()[origin]?.scope ?? "origin") === "request") return "per-request";
    if (deps.local.get(key(origin)) === "always") return "always";
    const session = deps.session.get(key(origin));
    return session === "allow" ? "session-allow" : session === "deny" ? "session-deny" : "ask";
  };

  return {
    state,
    declared: deps.declared,
    forget(origin) {
      deps.local.del(key(origin));
      deps.session.del(key(origin));
    },
    async request(origin, options = {}) {
      const def = definition(origin);
      const question: ConsentQuestion = {
        origin, purpose: purposeText(def.purpose, deps.lang), scope: def.scope ?? "origin",
        referrer: def.referrerPolicy ?? "no-referrer",
        ...(options.disclose !== undefined ? { disclose: options.disclose } : {}),
      };
      if (question.scope === "request") {
        // Invariant: request-scoped origins receive user input; without the
        // exact value the user cannot judge what leaves the device.
        if (!options.disclose) {
          throw new Error(`Origin ${origin} is declared "scope": "request": pass { disclose } with the exact value sent`);
        }
        return (await deps.ask(question)) === "once";
      }
      const current = state(origin);
      if (current !== "ask") return current !== "session-deny";
      let answer = pending.get(origin);
      if (!answer) {
        answer = deps.ask(question).then(choice => {
          pending.delete(origin);
          if (choice === "always") deps.local.set(key(origin), "always");
          const allowed = choice !== "deny";
          deps.session.set(key(origin), allowed ? "allow" : "deny");
          return allowed;
        });
        pending.set(origin, answer);
      }
      return answer;
    },
  };
}
