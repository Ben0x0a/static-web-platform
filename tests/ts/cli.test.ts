/*
  cli.test.ts — unit tests of the command-line frame (arguments, help, version,
  input, output, exit codes) with in-memory I/O.
  Used by : `npm test`.
  Uses    : src/cli/run.ts.
*/
import assert from "node:assert/strict";
import test from "node:test";
import { EXIT, runCli, type CliIo, type CliSpec } from "../../src/cli/run.ts";

const BUILD = { version: "abc123def456", date: "2026-11-09" };

const SPEC: CliSpec = {
  name: "tool", summary: "Counts things",
  commands: [
    { name: "count", summary: "Count the bytes of a file", input: "file",
      options: [{ name: "times", description: "Multiplier", type: "number", default: 1 },
                { name: "label", description: "Label", type: "string" },
                { name: "verbose", description: "More fields", type: "boolean" }],
      run: (input, options) => input && input.length > 0
        ? { ok: true, value: { bytes: input.length * Number(options["times"]), label: options["label"] ?? null,
                               verbose: options["verbose"] } }
        : { ok: false, code: "empty", message: "the file is empty" },
      text: value => `${(value as { bytes: number }).bytes} bytes\n` },
    { name: "list", summary: "List the units", input: "none", run: () => ({ ok: true, value: ["b", "kB"] }) },
  ],
};

interface Memory extends CliIo { stdout: string; stderr: string; written: Map<string, string> }

function memory(files: Record<string, string> = {}, stdin = ""): Memory {
  const io: Memory = {
    stdout: "", stderr: "", written: new Map(Object.entries(files)),
    readFile: async path => io.written.has(path)
      ? { ok: true, bytes: new TextEncoder().encode(io.written.get(path)) }
      : { ok: false, reason: "not found" },
    readStdin: async () => new TextEncoder().encode(stdin),
    out: async text => { io.stdout += text; },
    err: async text => { io.stderr += text; },
    writeFile: async (path, text, force) => {
      if (io.written.has(path) && !force) return { ok: false, reason: "exists", exists: true };
      io.written.set(path, text);
      return { ok: true };
    },
  };
  return io;
}

const run = (args: string[], io = memory({ "a.bin": "hello" })) => runCli(SPEC, args, BUILD, io).then(code => ({ code, io }));

test("help lists the commands in declared (workflow) order", async () => {
  const { code, io } = await run(["--help"]);
  assert.equal(code, EXIT.ok);
  assert.ok(io.stdout.indexOf("count") < io.stdout.indexOf("list"));
});

test("no arguments: usage on standard error, usage exit code", async () => {
  const { code, io } = await run([]);
  assert.equal(code, EXIT.usage);
  assert.match(io.stderr, /Usage: tool <command>/);
});

test("version prints the build version and date", async () => {
  const { code, io } = await run(["--version"]);
  assert.equal(code, EXIT.ok);
  assert.equal(io.stdout, "tool abc123def456 (2026-11-09)\n");
});

test("a command reads its file and prints JSON by default", async () => {
  const { code, io } = await run(["count", "a.bin", "--times", "2", "--label=x", "--verbose"]);
  assert.equal(code, EXIT.ok);
  assert.deepEqual(JSON.parse(io.stdout), { bytes: 10, label: "x", verbose: true });
});

test("--format text uses the command's text rendering", async () => {
  const { io } = await run(["count", "--format", "text", "a.bin"]);
  assert.equal(io.stdout, "5 bytes\n");
});

test("\"-\" reads standard input", async () => {
  const { code, io } = await run(["count", "-"], memory({}, "abc"));
  assert.equal(code, EXIT.ok);
  assert.equal(JSON.parse(io.stdout).bytes, 3);
});

test("an expected failure is an invalid-input exit with its code", async () => {
  const { code, io } = await run(["count", "-"], memory({}, ""));
  assert.equal(code, EXIT.invalidInput);
  assert.match(io.stderr, /count: empty: the file is empty/);
});

test("unreadable file is an invalid-input exit", async () => {
  const { code, io } = await run(["count", "missing.bin"]);
  assert.equal(code, EXIT.invalidInput);
  assert.match(io.stderr, /cannot read missing\.bin: not found/);
});

test("usage errors: unknown command, unknown option, bad number, missing or extra input", async () => {
  for (const args of [["nope"], ["count", "--nope", "a.bin"], ["count", "--times", "x", "a.bin"],
                      ["count"], ["count", "a.bin", "b.bin"], ["list", "a.bin"], ["count", "--format", "xml", "a.bin"],
                      ["count", "--force", "a.bin"]]) {
    const { code } = await run(args);
    assert.equal(code, EXIT.usage, args.join(" "));
  }
});

test("--out writes the result and never replaces a file without --force", async () => {
  const io = memory({ "a.bin": "hello", "out.json": "old" });
  assert.equal(await runCli(SPEC, ["count", "a.bin", "--out", "out.json"], BUILD, io), EXIT.usage);
  assert.equal(io.written.get("out.json"), "old");
  assert.equal(await runCli(SPEC, ["count", "a.bin", "--out", "out.json", "--force"], BUILD, io), EXIT.ok);
  assert.equal(JSON.parse(io.written.get("out.json") ?? "").bytes, 5);
  assert.equal(io.stdout, "");
});

test("a command with no input takes none", async () => {
  const { code, io } = await run(["list"]);
  assert.equal(code, EXIT.ok);
  assert.deepEqual(JSON.parse(io.stdout), ["b", "kB"]);
});
