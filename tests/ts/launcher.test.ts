/*
  launcher.test.ts — unit tests of the local-server launcher's request handling
  (host check, path rules, _headers) without opening a socket.
  Used by : `npm test`.
  Uses    : src/launcher/serve.ts (handle, parseHeaders, portArgument, candidatePorts).
*/
import assert from "node:assert/strict";
import test from "node:test";
import { candidatePorts, handle, parseHeaders, portArgument, type Site } from "../../src/launcher/serve.ts";

const FILES: Record<string, string> = { "/index.html": "<p>home</p>", "/app.js": "run()", "/version.json": "{}" };
const SITE: Site = {
  port: 8787,
  rules: parseHeaders("# comment\n/*\n  X-Content-Type-Options: nosniff\n/version.json\n  Cache-Control: no-store\n"),
  read: async path => path in FILES ? new TextEncoder().encode(FILES[path]) : null,
};

const get = (path: string, host = "127.0.0.1:8787", method = "GET") =>
  handle(new Request(`http://${host}${path}`, { method, headers: { host } }), SITE);

test("serves index.html for / with its type and the _headers rules", async () => {
  const response = await get("/");
  assert.equal(response.status, 200);
  assert.equal(await response.text(), "<p>home</p>");
  assert.match(response.headers.get("content-type") ?? "", /^text\/html/);
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
});

test("a more specific rule applies after the general one", async () => {
  assert.equal((await get("/version.json")).headers.get("cache-control"), "no-store");
});

test("only this machine's own host names are answered (DNS rebinding)", async () => {
  assert.equal((await get("/", "localhost:8787")).status, 200);
  assert.equal((await get("/", "evil.example:8787")).status, 421);
  assert.equal((await get("/", "127.0.0.1:9999")).status, 421);
});

test("no way out of public/", async () => {
  // Dot segments are resolved by the URL parser before handle() sees them: they stay inside.
  assert.equal((await get("/%2e%2e/%2e%2e/index.html")).status, 200);
  // Encoded separators survive URL parsing and become ".." or "\\" once decoded: refused.
  for (const path of ["/a%2f..%2f..%2fsecret", "/a%5c..%5csecret", "/a%00b"]) {
    assert.equal((await get(path)).status, 400, path);
  }
});

test("missing files, other methods, HEAD", async () => {
  assert.equal((await get("/nope.js")).status, 404);
  assert.equal((await get("/", "127.0.0.1:8787", "POST")).status, 405);
  const head = await get("/app.js", "127.0.0.1:8787", "HEAD");
  assert.equal(head.status, 200);
  assert.equal(await head.text(), "");
});

test("on port 80 the browser omits the port from Host", async () => {
  const site80: Site = { ...SITE, port: 80 };
  const at = (host: string) => handle(new Request(`http://${host}/`, { headers: { host } }), site80);
  assert.equal((await at("127.0.0.1")).status, 200);
  assert.equal((await at("localhost:80")).status, 200);
  assert.equal((await at("evil.example")).status, 421);
});

test("--port N and --port=N, validated", () => {
  assert.equal(portArgument([]), null);
  assert.equal(portArgument(["--port", "29500"]), 29500);
  assert.equal(portArgument(["--port=29500"]), 29500);
  for (const bad of [["--port"], ["--port", "x"], ["--port=0"], ["--port=70000"], ["--port=1e3"]]) {
    assert.equal(typeof portArgument(bad), "string", bad.join(" "));
  }
});

test("ports are tried from the app's default through its block, wrapping round", () => {
  assert.deepEqual(candidatePorts(29997, 29995, 29998), [29997, 29998, 29995, 29996]);
});

test("no CORS header is ever sent", async () => {
  assert.equal((await get("/app.js")).headers.get("access-control-allow-origin"), null);
});
