/*
  filter.test.ts — unit tests of the app's pure core (no browser needed).
  Used by : `npm test` (Node's test runner executes the .ts sources directly).
  Uses    : src/core/filter.ts.
*/
import assert from "node:assert/strict";
import test from "node:test";
import { matches, normalise } from "../src/core/filter.ts";

test("normalise removes accents and case", () => {
  assert.equal(normalise("  Café CRÈME "), "cafe creme");
});

test("every query word must match one of the fields", () => {
  assert.equal(matches("cafe creme", ["Café crème", "https://example.org"]), true);
  assert.equal(matches("cafe noir", ["Café crème"]), false);
  assert.equal(matches("   ", ["anything"]), true);
});
