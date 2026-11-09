/// <reference path="../cli/deno-io.d.ts" />
/// <reference path="./deno-serve.d.ts" />
/*
  launcher/serve.ts — the local-server launcher shipped in every
  "local-server" zip: serves the app's files on 127.0.0.1 only.

  Defines : handle() (one request), parseHeaders(), and the start-up below.
  Used by : bundle.bundle_launcher → serve.js in <id>-local.zip, run as
            `deno run --no-config --no-prompt --allow-net=127.0.0.1 --allow-read=. serve.js [--port N]`
            from the unzipped folder; gate.py (local-server checks).
  Uses    : the Deno APIs of cli/deno-io.d.ts and deno-serve.d.ts; the copy's
            serve.json (its default port and port range, written by the build),
            public/ folder and _headers file.

  Port: each app has its own default port (serve.json), inside a block the IANA
  registry leaves unassigned, so it collides neither with common tools nor with
  another app's copy. The port is part of the page's origin, and the browser
  keeps the page's saved data per origin: a stable default keeps that data
  reachable. When the default is taken, the next free port of the block is used
  (and said, since saved data does not follow); --port N forces one.

  Rules (the same as the hosted site, minus everything a local copy must not do):
  - binds 127.0.0.1, never 0.0.0.0: other machines cannot reach it;
  - answers only requests whose Host is 127.0.0.1:<port> or localhost:<port>
    (a web page using DNS rebinding to aim at this port is refused);
  - applies public/_headers (the CSP and the other security headers), so the
    page behaves as on the site; sends no CORS header, so other pages open in
    the browser cannot read its answers;
  - serves files only from public/, refuses "..", GET and HEAD only;
  - prints one start-up line and nothing else (no request log).
*/

const CONTENT_TYPES: Record<string, string> = {
  html: "text/html; charset=utf-8", js: "text/javascript; charset=utf-8", css: "text/css; charset=utf-8",
  json: "application/json; charset=utf-8", webmanifest: "application/manifest+json; charset=utf-8",
  svg: "image/svg+xml", png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif",
  webp: "image/webp", avif: "image/avif", ico: "image/x-icon", woff: "font/woff", woff2: "font/woff2",
  txt: "text/plain; charset=utf-8", wasm: "application/wasm",
};

export type HeaderRule = { pattern: RegExp; headers: [string, string][] };

/** Cloudflare-style _headers: an unindented URL pattern, then indented "Name: value" lines. */
export function parseHeaders(text: string): HeaderRule[] {
  const rules: HeaderRule[] = [];
  for (const raw of text.split("\n")) {
    if (!raw.trim() || raw.trimStart().startsWith("#")) continue;
    if (!/^\s/.test(raw)) {
      // "*" matches any characters, as in Cloudflare's rules and fnmatch.
      const source = raw.trim().split("*").map(part => part.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*");
      rules.push({ pattern: new RegExp(`^${source}$`), headers: [] });
    } else if (rules.length > 0 && raw.includes(":")) {
      const at = raw.indexOf(":");
      rules[rules.length - 1]?.headers.push([raw.slice(0, at).trim(), raw.slice(at + 1).trim()]);
    }
  }
  return rules;
}

export interface Site {
  port: number;
  rules: HeaderRule[];
  read(path: string): Promise<Uint8Array<ArrayBuffer> | null>;
}

/** Answer one request (pure apart from site.read, so it can be tested without a socket). */
export async function handle(request: Request, site: Site): Promise<Response> {
  const host = request.headers.get("host");
  // Invariant: only this machine's own names reach the files — see "Rules" above.
  // Browsers leave the port out of Host on the scheme's default port (80).
  const names = ["127.0.0.1", "localhost"];
  const allowed = names.map(name => `${name}:${site.port}`).concat(site.port === 80 ? names : []);
  if (!allowed.includes(host ?? "")) {
    return new Response("Unknown host\n", { status: 421 });
  }
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method not allowed\n", { status: 405, headers: { allow: "GET, HEAD" } });
  }
  let path: string;
  try { path = decodeURIComponent(new URL(request.url).pathname); }
  catch { return new Response("Bad request\n", { status: 400 }); }
  // Invariant: no way out of public/ (a "..", a NUL or a backslash would be).
  if (path.split("/").includes("..") || path.includes("\0") || path.includes("\\")) {
    return new Response("Bad request\n", { status: 400 });
  }
  if (path.endsWith("/")) path += "index.html";
  const body = await site.read(path);
  if (body === null) return new Response("Not found\n", { status: 404 });
  const headers = new Headers({ "content-type": CONTENT_TYPES[path.split(".").pop() ?? ""] ?? "application/octet-stream",
                                "cache-control": "no-cache" });
  for (const rule of site.rules) {
    if (rule.pattern.test(path)) for (const [name, value] of rule.headers) headers.set(name, value);
  }
  return new Response(request.method === "HEAD" ? null : body, { headers });
}

/** The port asked for with --port N or --port=N; null when absent; an error message when invalid. */
export function portArgument(args: string[]): number | null | string {
  const at = args.findIndex(arg => arg === "--port" || arg.startsWith("--port="));
  if (at === -1) return null;
  const arg = args[at] ?? "";
  const raw = arg.startsWith("--port=") ? arg.slice("--port=".length) : args[at + 1] ?? "";
  const value = Number(raw);
  return /^\d+$/.test(raw) && value >= 1 && value <= 65535 ? value : "--port must be a number between 1 and 65535";
}

/** Ports to try, in order: the default, then the rest of its block (wrapping round). */
export function candidatePorts(port: number, first: number, last: number): number[] {
  const size = last - first + 1;
  return Array.from({ length: size }, (_, i) => first + ((port - first + i) % size));
}

const TRIES = 20;     // enough to step over a few taken ports, few enough to fail fast

async function main(): Promise<number> {
  const decoder = new TextDecoder();
  const fail = (message: string): number => { console.error(message); return 1; };
  const rootDir = `${import.meta.dirname}/public`;
  const read = async (path: string): Promise<Uint8Array<ArrayBuffer> | null> => {
    try { return await Deno.readFile(rootDir + path); }
    catch (err) {
      // A folder is not a page; anything else unexpected becomes a 500 in handle()'s caller.
      if (err instanceof Deno.errors.NotFound || err instanceof Deno.errors.IsADirectory) return null;
      throw err;
    }
  };
  let config: { port: number; first: number; last: number };
  let headersFile: Uint8Array | null;
  try {
    config = JSON.parse(decoder.decode(await Deno.readFile(`${import.meta.dirname}/serve.json`)));
    headersFile = await read("/_headers");
  } catch (err) {
    if (err instanceof Deno.errors.NotCapable || err instanceof Deno.errors.NotFound) {
      return fail(`Cannot read this copy's files. Start it from its own folder:\n  cd "${import.meta.dirname}"\n`
                  + "  deno run --no-config --no-prompt --allow-net=127.0.0.1 --allow-read=. serve.js");
    }
    throw err;
  }
  const rules = parseHeaders(headersFile ? decoder.decode(headersFile) : "");
  const asked = portArgument(Deno.args);
  if (typeof asked === "string") return fail(asked);
  const ports = asked !== null ? [asked] : candidatePorts(config.port, config.first, config.last).slice(0, TRIES);
  for (const port of ports) {
    const site: Site = { port, rules, read };
    try {
      Deno.serve({
        hostname: "127.0.0.1", port,
        onListen: () => {
          if (port !== ports[0]) console.log(`Port ${ports[0]} is in use: data saved in the page at that port is not visible here.`);
          console.log(`Serving on http://127.0.0.1:${port}/ (Ctrl+C to stop)`);
        },
      }, request => handle(request, site).catch(() => new Response("Internal error\n", { status: 500 })));
      return 0;
    } catch (err) {
      if (!(err instanceof Deno.errors.AddrInUse)) throw err;
    }
  }
  return fail(asked !== null ? `Port ${asked} is in use: choose another with --port.`
                             : `Ports ${ports[0]}–${ports[ports.length - 1]} are in use: choose one with --port.`);
}

if (import.meta.main) {
  const code = await main();
  if (code !== 0) Deno.exit(code);
}
