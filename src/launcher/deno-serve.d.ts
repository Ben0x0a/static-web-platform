/*
  launcher/deno-serve.d.ts — the Deno APIs the local-server launcher adds to
  cli/deno-io.d.ts (type declarations only).

  Defines : Deno.serve (HTTP server), Deno.errors.AddrInUse / IsADirectory,
            ImportMeta.dirname.
  Used by : launcher/serve.ts (triple-slash reference). Never referenced from
            cli/: an app's command line must not be able to listen or connect.
  Uses    : nothing. Request / Response come from TypeScript's DOM library,
            which the platform's own type check includes.

  Signatures mirror Deno 2.9 (lib.deno.ns.d.ts), narrowed to what serve.ts needs.
*/

declare namespace Deno {
  interface ServeOptions {
    hostname: string;
    port: number;
    /** Called once the socket is bound. */
    onListen?(addr: { hostname: string; port: number }): void;
  }
  /** Throws Deno.errors.AddrInUse when the port is taken. */
  function serve(options: ServeOptions, handler: (request: Request) => Response | Promise<Response>): unknown;
  namespace errors {
    class AddrInUse extends Error {}
    class IsADirectory extends Error {}
  }
}

interface ImportMeta {
  /** Absolute directory of this module (Deno). */
  dirname: string;
}
