/*
  core.test.ts — unit tests of the pure core (i18n, registry, version).
  Used by : `npm test` (Node's test runner executes the .ts sources directly).
  Uses    : src/core/*.
*/
import assert from "node:assert/strict";
import test from "node:test";
import { createI18n } from "../../src/core/i18n.ts";
import { createRegistry } from "../../src/core/registry.ts";
import { displayDate, isUpdateAvailable } from "../../src/core/version.ts";

test("i18n fills placeholders and merges app strings over platform strings", () => {
  const i18n = createI18n("fr", { fr: { hello: "Bonjour {name}", bye: "Au revoir" } });
  i18n.add({ fr: { bye: "Salut" } });
  assert.equal(i18n.t("hello", { name: "Ana" }), "Bonjour Ana");
  assert.equal(i18n.t("bye"), "Salut");
});

test("i18n throws on a missing key instead of showing 'undefined'", () => {
  const i18n = createI18n("en", { fr: { only: "fr" } });
  assert.throws(() => i18n.t("only"), /Missing UI string "only" for language "en"/);
});

type Spec = { type: "a"; n: number } | { type: "b"; s: string };

test("registry renders each spec with the renderer of its type", () => {
  const registry = createRegistry<Spec, string, null>();
  registry.register("a", spec => `A${spec.n}`);
  registry.register("b", spec => `B${spec.s}`);
  assert.equal(registry.render({ type: "a", n: 1 }, null), "A1");
  assert.equal(registry.render({ type: "b", s: "x" }, null), "Bx");
  assert.deepEqual(registry.types(), ["a", "b"]);
});

test("registry rejects double registration and unknown types", () => {
  const registry = createRegistry<Spec, string, null>();
  registry.register("a", () => "");
  assert.throws(() => registry.register("a", () => ""), /registered twice/);
  assert.throws(() => registry.render({ type: "b", s: "" }, null), /No renderer registered for type "b"/);
});

test("version helpers", () => {
  const info = { version: "abc", date: "2026-10-03", download: "x.html", sha256: "" };
  assert.equal(isUpdateAvailable("abc", info), false);
  assert.equal(isUpdateAvailable("abd", info), true);
  assert.equal(displayDate("2026-10-03"), "03.10.2026");
});
