/*
  services/workers.ts — start a declared Web Worker the same way in both outputs.

  Defines : startWorker().
  Used by : platform.ts (platform.worker(name)).
  Uses    : core/types.ts (SiteConfig); in the single file, the inert
            <script type="text/plain" id="swp-worker-<name>"> written by the build.

  Site: new Worker("workers/<name>.js") (CSP worker-src 'self').
  Single file: the worker's code is inlined as inert text and started from a
  blob: URL — the only case where that file's CSP allows worker-src blob:.
*/
import type { SiteConfig } from "../core/types.ts";

export function startWorker(site: SiteConfig<unknown>, name: string): Worker {
  // Invariant: only workers declared in site.json are built and published.
  if (!site.workers.includes(name)) throw new Error(`Undeclared worker: ${name} (site.json "workers")`);
  if (site.mode === "site") return new Worker(`workers/${name}.js`);
  const source = document.getElementById(`swp-worker-${name}`)?.textContent;
  // Invariant: the build inlines every declared worker into the single file.
  if (!source) throw new Error(`Worker ${name} missing from the single file`);
  return new Worker(URL.createObjectURL(new Blob([source], { type: "text/javascript" })));
}
