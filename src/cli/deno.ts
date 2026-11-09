/// <reference path="./deno-io.d.ts" />
/*
  cli/deno.ts — runs an app's command-line spec under Deno.

  Defines : startCli(), denoIo().
  Used by : apps' src/cli/main.ts through "static-web-platform/cli".
  Uses    : cli/run.ts; the Deno APIs declared in cli/deno-io.d.ts (nothing else,
            so the CLI bundle has no network code); __SWP_VERSION__ and
            __SWP_DATE__, set by `swp build`.

  WHY start only when import.meta.main is true: the same bundle is also the
  app's library (`import { analyse } from "./<id>-cli.js"`); importing it must
  not parse the importer's arguments or exit its process.
*/
import { EXIT, runCli, type CliIo, type CliSpec, type ReadResult, type WriteResult } from "./run.ts";

const encoder = new TextEncoder();

async function writeAll(stream: { write(p: Uint8Array): Promise<number> }, text: string): Promise<void> {
  // HOW: a write may be partial (pipes); loop until every byte is written.
  let bytes = encoder.encode(text);
  while (bytes.length > 0) bytes = bytes.subarray(await stream.write(bytes));
}

function reasonOf(err: unknown): string {
  if (err instanceof Deno.errors.NotFound) return "not found";
  if (err instanceof Deno.errors.NotCapable) return "not allowed (run Deno with --allow-read / --allow-write for it)";
  if (err instanceof Deno.errors.PermissionDenied) return "permission denied";
  return err instanceof Error ? err.message : String(err);
}

/** The real I/O: local files and the standard streams. */
export function denoIo(): CliIo {
  return {
    async readFile(path: string): Promise<ReadResult> {
      try { return { ok: true, bytes: await Deno.readFile(path) }; }
      catch (err) { return { ok: false, reason: reasonOf(err) }; }
    },
    async readStdin(): Promise<Uint8Array> {
      const chunks: Uint8Array[] = [];
      let total = 0;
      for (;;) {
        const buffer = new Uint8Array(65536);
        const n = await Deno.stdin.read(buffer);
        if (n === null) break;
        chunks.push(buffer.subarray(0, n));
        total += n;
      }
      const all = new Uint8Array(total);
      let offset = 0;
      for (const chunk of chunks) { all.set(chunk, offset); offset += chunk.length; }
      return all;
    },
    out: text => writeAll(Deno.stdout, text),
    err: text => writeAll(Deno.stderr, text),
    async writeFile(path: string, text: string, force: boolean): Promise<WriteResult> {
      try {
        await Deno.writeFile(path, encoder.encode(text), { createNew: !force });
        return { ok: true };
      } catch (err) {
        return { ok: false, reason: reasonOf(err), exists: err instanceof Deno.errors.AlreadyExists };
      }
    },
  };
}

/** Run `spec` with the process arguments, then exit — only when this bundle is the entry point. */
export function startCli(spec: CliSpec): void {
  if (!import.meta.main) return;
  const io = denoIo();
  runCli(spec, Deno.args, { version: __SWP_VERSION__, date: __SWP_DATE__ }, io)
    .then(code => Deno.exit(code))
    .catch(async (err: unknown) => {
      // A command threw instead of returning a CliOutcome: a bug, not an input problem.
      await io.err(`${spec.name}: internal error: ${err instanceof Error ? err.stack ?? err.message : String(err)}\n`);
      Deno.exit(EXIT.internal);
    });
}
