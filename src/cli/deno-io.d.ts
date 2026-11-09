/*
  cli/deno-io.d.ts — the only Deno APIs an app's command-line shell may use
  (type declarations only).

  Defines : Deno.args, readFile, writeFile, stdin/stdout/stderr, exit, the
            error classes they throw; ImportMeta.main; the build-time constants
            __SWP_VERSION__ and __SWP_DATE__ (esbuild --define).
  Used by : cli/deno.ts (triple-slash reference), hence every app's cli/ through
            "static-web-platform/cli"; bundle.check_pure_layers type-checks cli/
            against this file and core-runtime.d.ts only.
  Uses    : nothing.

  WHY a curated subset instead of Deno's full types: whatever is not declared
  here does not type-check in cli/. Network APIs (fetch, Deno.connect,
  Deno.listen, Deno.serve, Deno.Command…) are deliberately absent, so a
  command that tries to reach the network fails the build. Deno itself is the
  second barrier: the CLI runs without --allow-net. Signatures mirror Deno 2.9
  (lib.deno.ns.d.ts), narrowed to what cli/deno.ts needs.
*/

declare namespace Deno {
  /** Command-line arguments, without the runtime and the script name. */
  const args: string[];
  function readFile(path: string): Promise<Uint8Array<ArrayBuffer>>;
  /** createNew: fail with AlreadyExists instead of overwriting. */
  function writeFile(path: string, data: Uint8Array, options?: { createNew?: boolean }): Promise<void>;
  /** Reads up to p.length bytes; null at end of input. */
  const stdin: { read(p: Uint8Array): Promise<number | null> };
  /** Writes may be partial: the return value is the number of bytes written. */
  const stdout: { write(p: Uint8Array): Promise<number> };
  const stderr: { write(p: Uint8Array): Promise<number> };
  function exit(code?: number): never;
  namespace errors {
    class NotFound extends Error {}
    class AlreadyExists extends Error {}
    /** Operating-system refusal (file mode, ownership). */
    class PermissionDenied extends Error {}
    /** Deno sandbox refusal: the permission flag (--allow-read…) was not given. */
    class NotCapable extends Error {}
  }
}

interface ImportMeta {
  /** True when this module is the program's entry point (not imported). */
  main: boolean;
}

/** The app version (hash of the sources), set by `swp build`. */
declare const __SWP_VERSION__: string;
/** The build date (YYYY-MM-DD), set by `swp build`. */
declare const __SWP_DATE__: string;
