/*
  cli/run.ts — the command-line frame shared by every app: arguments, help,
  version, input, output and exit codes (runtime-neutral: all I/O injected).

  Defines : runCli(), EXIT, and the types an app's cli/ declares its commands
            with (CliSpec, CliCommand, CliOption, CliOutcome) plus CliIo.
  Used by : cli/deno.ts (startCli, with the real Deno I/O); tests/ts/cli.test.ts
            (in-memory I/O); apps through cli/index.ts.
  Uses    : nothing.

  Grammar:  <name> --help | --version
            <name> <command> [--<option> value | --<flag>] [--format json|text]
                             [--out FILE [--force]] [FILE | -]
  The app only lists its commands (in workflow order, as `--help` shows them);
  each command is a thin adapter calling one operation of the app's api/.
  WHY one frame for every app: the same flags, help layout and exit codes
  everywhere, and no argument parsing to get wrong in each app.
*/

/** Exit codes (documented in every app's README through the platform's). */
export const EXIT = { ok: 0, invalidInput: 1, usage: 2, internal: 3 } as const;

export type CliValue = string | number | boolean;

export interface CliOption {
  /** Long name, without the dashes: "max-depth" → --max-depth. */
  name: string;
  description: string;
  type: "string" | "number" | "boolean";
  /** Value when the option is absent; a boolean option defaults to false. */
  default?: CliValue;
}

/** What a command returns: a result, or an expected failure with a stable code. */
export type CliOutcome = { ok: true; value: unknown } | { ok: false; code: string; message: string };

export interface CliCommand {
  /** Same name as the api/ operation it calls. */
  name: string;
  summary: string;
  /**
   * "file": one input, a path or "-" for standard input, passed as bytes.
   * "none": no input (the options carry everything, e.g. a lookup in a dataset).
   */
  input: "file" | "none";
  options?: CliOption[];
  run(input: Uint8Array | null, options: Record<string, CliValue>): CliOutcome | Promise<CliOutcome>;
  /** Rendering for --format text; JSON when absent. */
  text?(value: unknown): string;
}

export interface CliSpec {
  /** The command people type (the script name in the README examples). */
  name: string;
  summary: string;
  commands: CliCommand[];
}

export type ReadResult = { ok: true; bytes: Uint8Array } | { ok: false; reason: string };
export type WriteResult = { ok: true } | { ok: false; reason: string; exists: boolean };

/** Everything runCli needs from the outside world. */
export interface CliIo {
  readFile(path: string): Promise<ReadResult>;
  readStdin(): Promise<Uint8Array>;
  out(text: string): Promise<void>;
  err(text: string): Promise<void>;
  /** Refuses to replace an existing file unless force is true (exists: true). */
  writeFile(path: string, text: string, force: boolean): Promise<WriteResult>;
}

export interface BuildInfo {
  version: string;
  date: string;
}

const FORMATS = ["json", "text"] as const;
type Format = (typeof FORMATS)[number];

interface Parsed {
  options: Record<string, CliValue>;
  format: Format;
  out: string | null;
  force: boolean;
  help: boolean;
  inputs: string[];
}

type ParseResult = { ok: true; parsed: Parsed } | { ok: false; message: string };

function usage(spec: CliSpec): string {
  const width = Math.max(...spec.commands.map(c => c.name.length));
  return [
    `${spec.name} — ${spec.summary}`, "",
    `Usage: ${spec.name} <command> [options] [FILE | -]`,
    `       ${spec.name} <command> --help | --help | --version`, "",
    "Commands:",
    ...spec.commands.map(c => `  ${c.name.padEnd(width)}  ${c.summary}`), "",
  ].join("\n");
}

function commandUsage(spec: CliSpec, command: CliCommand): string {
  const input = command.input === "file" ? " FILE | -" : "";
  const lines = [`${spec.name} ${command.name} — ${command.summary}`, "",
    `Usage: ${spec.name} ${command.name} [options]${input}`, "", "Options:"];
  for (const option of command.options ?? []) {
    const value = option.type === "boolean" ? "" : ` <${option.type}>`;
    const fallback = option.default === undefined ? "" : ` (default: ${String(option.default)})`;
    lines.push(`  --${option.name}${value}  ${option.description}${fallback}`);
  }
  lines.push("  --format json|text  output format (default: json)",
    "  --out FILE  write the result to FILE instead of standard output",
    "  --force  with --out: replace FILE if it exists", "");
  if (command.input === "file") lines.push("FILE is read locally; \"-\" reads standard input.", "");
  return lines.join("\n");
}

function parseValue(option: CliOption, raw: string): CliValue | null {
  if (option.type === "string") return raw;
  if (option.type === "number") {
    const value = Number(raw);
    return raw.trim() !== "" && Number.isFinite(value) ? value : null;
  }
  return raw === "true" ? true : raw === "false" ? false : null;
}

function parseArgs(command: CliCommand, args: string[]): ParseResult {
  // HOW: one left-to-right pass; "--name=value" and "--name value" both work;
  // a lone "-" or anything not starting with "--" is an input.
  const declared = new Map((command.options ?? []).map(o => [o.name, o]));
  const options: Record<string, CliValue> = {};
  for (const option of command.options ?? []) {
    if (option.default !== undefined) options[option.name] = option.default;
    else if (option.type === "boolean") options[option.name] = false;
  }
  const parsed: Parsed = { options, format: "json", out: null, force: false, help: false, inputs: [] };
  for (let i = 0; i < args.length; i++) {
    const arg = args[i] ?? "";
    if (arg === "-" || !arg.startsWith("--")) { parsed.inputs.push(arg); continue; }
    const eq = arg.indexOf("=");
    const name = arg.slice(2, eq === -1 ? undefined : eq);
    const inline = eq === -1 ? null : arg.slice(eq + 1);
    const next = (): string | null => {
      if (inline !== null) return inline;
      const value = args[i + 1];
      if (value === undefined) return null;
      i++;
      return value;
    };
    if (name === "help") { parsed.help = true; continue; }
    if (name === "force") { parsed.force = true; continue; }
    if (name === "format" || name === "out") {
      const value = next();
      if (value === null) return { ok: false, message: `--${name} needs a value` };
      if (name === "out") parsed.out = value;
      else if ((FORMATS as readonly string[]).includes(value)) parsed.format = value as Format;
      else return { ok: false, message: `--format must be one of ${FORMATS.join(", ")}` };
      continue;
    }
    const option = declared.get(name);
    if (!option) return { ok: false, message: `unknown option --${name}` };
    if (option.type === "boolean" && inline === null) { parsed.options[name] = true; continue; }
    const raw = next();
    if (raw === null) return { ok: false, message: `--${name} needs a value` };
    const value = parseValue(option, raw);
    if (value === null) return { ok: false, message: `--${name}: "${raw}" is not a ${option.type}` };
    parsed.options[name] = value;
  }
  return { ok: true, parsed };
}

/** Run one invocation; resolves to the process exit code (EXIT). */
export async function runCli(spec: CliSpec, args: string[], build: BuildInfo, io: CliIo): Promise<number> {
  const [first, ...rest] = args;
  if (first === undefined) { await io.err(usage(spec)); return EXIT.usage; }
  if (first === "--help" || first === "-h") { await io.out(usage(spec)); return EXIT.ok; }
  if (first === "--version") { await io.out(`${spec.name} ${build.version} (${build.date})\n`); return EXIT.ok; }
  const fail = async (code: number, message: string): Promise<number> => {
    await io.err(`${spec.name}: ${message}\n`);
    return code;
  };
  const command = spec.commands.find(c => c.name === first);
  if (!command) return fail(EXIT.usage, `unknown command "${first}" (see ${spec.name} --help)`);
  const result = parseArgs(command, rest);
  if (!result.ok) return fail(EXIT.usage, `${command.name}: ${result.message}`);
  const parsed = result.parsed;
  if (parsed.help) { await io.out(commandUsage(spec, command)); return EXIT.ok; }
  if (parsed.force && parsed.out === null) return fail(EXIT.usage, `${command.name}: --force only applies with --out`);

  let input: Uint8Array | null = null;
  if (command.input === "file") {
    if (parsed.inputs.length !== 1) return fail(EXIT.usage, `${command.name}: expects exactly one FILE (or - for standard input)`);
    const path = parsed.inputs[0] ?? "-";
    if (path === "-") input = await io.readStdin();
    else {
      const read = await io.readFile(path);
      if (!read.ok) return fail(EXIT.invalidInput, `${command.name}: cannot read ${path}: ${read.reason}`);
      input = read.bytes;
    }
  } else if (parsed.inputs.length > 0) {
    return fail(EXIT.usage, `${command.name}: takes no FILE (got ${parsed.inputs.join(" ")})`);
  }

  const outcome = await command.run(input, parsed.options);
  if (!outcome.ok) return fail(EXIT.invalidInput, `${command.name}: ${outcome.code}: ${outcome.message}`);
  const text = parsed.format === "text" && command.text
    ? command.text(outcome.value)
    : `${JSON.stringify(outcome.value, null, 2)}\n`;
  if (parsed.out === null) { await io.out(text); return EXIT.ok; }
  const written = await io.writeFile(parsed.out, text, parsed.force);
  if (written.ok) return EXIT.ok;
  return written.exists
    ? fail(EXIT.usage, `${command.name}: ${parsed.out} exists (add --force to replace it)`)
    : fail(EXIT.invalidInput, `${command.name}: cannot write ${parsed.out}: ${written.reason}`);
}
