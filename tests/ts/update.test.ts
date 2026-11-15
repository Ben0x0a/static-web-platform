/*
  update.test.ts — unit tests of the local copies' update check: each copy is
  offered a new copy of its own kind (single file → single file, local server → zip).
  Used by : `npm test`.
  Uses    : src/services/update.ts (with a fake Network).
*/
import assert from "node:assert/strict";
import test from "node:test";
import type { PageMode, SiteConfig, VersionInfo } from "../../src/core/types.ts";
import type { Network } from "../../src/services/network.ts";
import { checkForUpdate } from "../../src/services/update.ts";

const INFO: VersionInfo = { version: "new", date: "2026-11-15", download: "app.html", sha256: "a",
                            local: { file: "app-local.zip", sha256: "b" } };

const site = (mode: PageMode, version = "old") =>
  ({ mode, version, siteUrl: "https://app.example/" }) as SiteConfig<unknown>;
const serving = (info: VersionInfo | null): Network =>
  ({ fetch: async () => info && new Response(JSON.stringify(info)) }) as unknown as Network;

test("a single file is offered the new single file", async () => {
  const result = await checkForUpdate(site("single"), serving(INFO));
  assert.deepEqual(result.kind === "available" && [result.file, result.downloadUrl],
                   ["app.html", "https://app.example/app.html"]);
});

test("a local-server copy is offered the new zip, never the single file", async () => {
  const result = await checkForUpdate(site("local"), serving(INFO));
  assert.deepEqual(result.kind === "available" && [result.file, result.downloadUrl],
                   ["app-local.zip", "https://app.example/app-local.zip"]);
});

test("a kind of copy the site no longer offers: no file, the link opens the site", async () => {
  const result = await checkForUpdate(site("local"), serving({ ...INFO, local: null }));
  assert.deepEqual(result.kind === "available" && [result.file, result.downloadUrl],
                   [null, "https://app.example/"]);
});

test("same version: up to date; consent refused: declined", async () => {
  assert.equal((await checkForUpdate(site("single", "new"), serving(INFO))).kind, "up-to-date");
  assert.equal((await checkForUpdate(site("single"), serving(null))).kind, "declined");
});
