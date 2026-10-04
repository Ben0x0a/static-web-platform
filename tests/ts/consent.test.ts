/*
  consent.test.ts — unit tests of the consent gate's decision logic, with
  in-memory stores and a scripted "user" instead of the dialog.
  Used by : `npm test`.
  Uses    : src/services/consent.ts, src/services/storage.ts.
*/
import assert from "node:assert/strict";
import test from "node:test";
import { createConsent, type ConsentAnswer } from "../../src/services/consent.ts";
import { createStore } from "../../src/services/storage.ts";

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() { return data.size; },
    clear: () => data.clear(),
    getItem: k => data.get(k) ?? null,
    key: i => [...data.keys()][i] ?? null,
    removeItem: k => { data.delete(k); },
    setItem: (k, v) => { data.set(k, v); },
  } as Storage;
}

function setup(answers: ConsentAnswer[], scope: "origin" | "request" = "origin") {
  const local = createStore("app", (() => { const s = memoryStorage(); return () => s; })());
  const session = createStore("app", (() => { const s = memoryStorage(); return () => s; })());
  const asked: string[] = [];
  const consent = createConsent({
    local, session, lang: "en",
    declared: () => ({ "https://icons.example": { directive: "img-src", purpose: { en: "Icons" }, scope } }),
    ask: async q => { asked.push(`${q.origin}|${q.purpose}|${q.scope}|${q.disclose ?? ""}`); return answers.shift() ?? "deny"; },
  });
  return { consent, asked };
}

test("undeclared origins are a bug: request() throws", async () => {
  const { consent } = setup([]);
  await assert.rejects(consent.request("https://evil.example"), /Undeclared external origin/);
});

test("deny is remembered for the session and not asked again", async () => {
  const { consent, asked } = setup(["deny"]);
  assert.equal(await consent.request("https://icons.example"), false);
  assert.equal(await consent.request("https://icons.example"), false);
  assert.equal(asked.length, 1);
  assert.equal(consent.state("https://icons.example"), "session-deny");
});

test("parallel requests share a single prompt", async () => {
  const { consent, asked } = setup(["session"]);
  const results = await Promise.all([1, 2, 3].map(() => consent.request("https://icons.example")));
  assert.deepEqual(results, [true, true, true]);
  assert.deepEqual(asked, ["https://icons.example|Icons|origin|"]);
});

test("always is persistent; forget() asks again", async () => {
  const { consent, asked } = setup(["always", "deny"]);
  assert.equal(await consent.request("https://icons.example"), true);
  assert.equal(consent.state("https://icons.example"), "always");
  consent.forget("https://icons.example");
  assert.equal(await consent.request("https://icons.example"), false);
  assert.equal(asked.length, 2);
});

test("scope request: the exact value is required and shown", async () => {
  const { consent, asked } = setup(["once"], "request");
  await assert.rejects(consent.request("https://icons.example"), /pass \{ disclose \}/);
  assert.equal(await consent.request("https://icons.example", { disclose: "sha256:abc" }), true);
  assert.deepEqual(asked, ["https://icons.example|Icons|request|sha256:abc"]);
});

test("scope request: nothing is remembered, every request asks", async () => {
  const { consent, asked } = setup(["once", "deny", "once"], "request");
  const results = await Promise.all(["a", "b", "c"].map(v => consent.request("https://icons.example", { disclose: v })));
  assert.deepEqual(results, [true, false, true]);
  assert.equal(asked.length, 3);
  assert.equal(consent.state("https://icons.example"), "per-request");
});
