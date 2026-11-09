/*
  core-runtime.d.ts — the runtime APIs src/core/, src/api/ and src/cli/ may use
  (type declarations only).

  Defines : TextEncoder, TextDecoder, structuredClone, crypto (getRandomValues,
            randomUUID, subtle.digest).
  Used by : bundle.check_pure_layers (added to the type checks of core/, api/
            and cli/, which otherwise have no DOM and no Node types).
  Uses    : nothing.

  WHY a curated list: core/ and api/ must run in the page, in Web Workers,
  in Node (unit tests) and in Deno (the CLI). These APIs exist in all four;
  TypeScript only declares them in its DOM library, which the purity check
  removes on purpose. Anything NOT listed here (document, window, fetch,
  storage…) stays an error in those layers. Extend this list only with APIs
  available in all four runtimes. Signatures mirror TypeScript's DOM library,
  narrowed to what these layers need.
*/

interface TextEncoderEncodeIntoResult { read: number; written: number }

declare class TextEncoder {
  readonly encoding: string;
  encode(input?: string): Uint8Array<ArrayBuffer>;
  encodeInto(source: string, destination: Uint8Array): TextEncoderEncodeIntoResult;
}

declare class TextDecoder {
  constructor(label?: string, options?: { fatal?: boolean; ignoreBOM?: boolean });
  readonly encoding: string;
  readonly fatal: boolean;
  readonly ignoreBOM: boolean;
  decode(input?: ArrayBuffer | ArrayBufferView, options?: { stream?: boolean }): string;
}

declare function structuredClone<T = any>(value: T, options?: { transfer?: unknown[] }): T;

interface CoreSubtleCrypto {
  /** SHA-1 / SHA-256 / SHA-384 / SHA-512 digest (evidence hashing). */
  digest(algorithm: string | { name: string }, data: ArrayBuffer | ArrayBufferView): Promise<ArrayBuffer>;
}

declare const crypto: {
  getRandomValues<T extends ArrayBufferView | null>(array: T): T;
  randomUUID(): `${string}-${string}-${string}-${string}-${string}`;
  readonly subtle: CoreSubtleCrypto;
};
