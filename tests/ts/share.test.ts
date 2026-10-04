/*
  share.test.ts — unit tests of share-link encoding (pure parts).
  Used by : `npm test`.
  Uses    : src/services/share.ts.
*/
import assert from "node:assert/strict";
import test from "node:test";
import { SHARE_PREFIX, decodeShare, encodeShare, shareLink } from "../../src/services/share.ts";

test("round trip keeps unicode and structure", () => {
  const payload = { title: "Météo — 日本", values: [1, 2.5, null], ok: true };
  assert.deepEqual(decodeShare(encodeShare(payload)), payload);
});

test("encoding is URL-fragment safe (base64url, no padding)", () => {
  assert.match(encodeShare({ x: "???>>>~~~" }), /^[A-Za-z0-9_-]+$/);
});

test("malformed input decodes to null instead of throwing", () => {
  assert.equal(decodeShare("%%%"), null);
  assert.equal(decodeShare(encodeShare("x").slice(0, 2)), null);
});

test("links drop any existing query and fragment from the base", () => {
  const link = shareLink("https://app.example/page?x=1#old", { a: 1 });
  assert.ok(link.startsWith(`https://app.example/page${SHARE_PREFIX}`));
});
