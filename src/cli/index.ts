/*! static-web-platform | Copyright 2026 Ben0x0a | Apache-2.0 | https://github.com/Ben0x0a/static-web-platform */
// The "/*!" comment above is a legal comment: bundlers keep it in every app's
// CLI bundle, so redistributed copies carry the licence notice (Apache-2.0 § 4).

/*
  cli/index.ts — public API of the platform's command-line entry
  ("static-web-platform/cli"), the only platform import an app's cli/ may use.

  Defines : the re-exports below; nothing else is public.
  Used by : apps' src/cli/main.ts: `startCli({ name, summary, commands })`.
  Uses    : cli/run.ts, cli/deno.ts.
*/
export { startCli } from "./deno.ts";
export { EXIT, runCli } from "./run.ts";
export type { BuildInfo, CliCommand, CliIo, CliOption, CliOutcome, CliSpec, CliValue } from "./run.ts";
