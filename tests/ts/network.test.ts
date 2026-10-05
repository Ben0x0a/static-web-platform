/*
  network.test.ts — unit tests of the network rules: consent first, credentials
  omitted, redirects never followed, images refuse request-scoped origins.
  Used by : `npm test`.
  Uses    : src/services/network.ts (with a fake fetch and a fake consent).
*/
import assert from "node:assert/strict";
import test from "node:test";
import type { Consent } from "../../src/services/consent.ts";
import { RedirectBlockedError, createNetwork } from "../../src/services/network.ts";

const declared = {
  "https://lookup.example": { directive: "connect-src" as const, purpose: "Look up", scope: "request" as const },
  "https://tiles.example": { directive: "img-src" as const, purpose: "Map", referrerPolicy: "strict-origin" as const },
};
const consent = (allow: boolean): Consent => ({
  request: async () => allow, state: () => "ask", forget: () => {}, declared: () => declared,
});
const reply = (status: number, type: ResponseType = "cors") => ({ status, type }) as Response;

test("refused consent: nothing is fetched", async () => {
  let calls = 0;
  const net = createNetwork(consent(false), async () => { calls++; return reply(200); });
  assert.equal(await net.fetch("https://lookup.example/x", {}, { disclose: "v" }), null);
  assert.equal(calls, 0);
});

test("credentials, referrer and redirect are forced, whatever the app passes", async () => {
  let seen: RequestInit = {};
  const net = createNetwork(consent(true), async (_url, init) => { seen = init ?? {}; return reply(200); });
  await net.fetch("https://lookup.example/x", { credentials: "include", redirect: "follow" }, { disclose: "v" });
  assert.equal(seen.credentials, "omit");
  assert.equal(seen.redirect, "manual");
  assert.equal(seen.referrerPolicy, "no-referrer");
});

test("a redirect is never followed: RedirectBlockedError", async () => {
  const net = createNetwork(consent(true), async () => reply(0, "opaqueredirect"));
  await assert.rejects(net.fetch("https://lookup.example/x", {}, { disclose: "v" }), RedirectBlockedError);
  const visible = createNetwork(consent(true), async () => reply(302));
  await assert.rejects(visible.fetch("https://lookup.example/x", {}, { disclose: "v" }), RedirectBlockedError);
});

test("images refuse request-scoped origins and fall back", async () => {
  const errors: string[] = [];
  const original = console.error;
  console.error = (m: string) => { errors.push(m); };
  let replaced = false;
  const img = { replaceWith: () => { replaced = true; } } as unknown as HTMLImageElement;
  try {
    await createNetwork(consent(true)).image(img, "https://lookup.example/x.png", () => ({}) as Element);
  } finally {
    console.error = original;
  }
  assert.equal(replaced, true);
  assert.match(errors[0] ?? "", /refuses https:\/\/lookup\.example/);
});
