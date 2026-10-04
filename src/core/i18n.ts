/*
  core/i18n.ts — UI strings: one language per app, missing keys fail loudly.

  Defines : createI18n() → { lang, t, add }.
  Used by : platform.ts (platform strings + app strings), apps via Platform.t.
  Uses    : nothing (pure).
*/

export type StringTable = Record<string, Record<string, string>>;

export interface I18n {
  readonly lang: string;
  /** Text for `key` with {placeholders} filled from `vars`. */
  t(key: string, vars?: Record<string, string | number>): string;
  /** Merge more strings (e.g. the app's own), per language. */
  add(table: StringTable): void;
}

export function createI18n(lang: string, base: StringTable): I18n {
  const tables: StringTable = {};
  const add = (table: StringTable): void => {
    for (const [code, strings] of Object.entries(table)) Object.assign(tables[code] ??= {}, strings);
  };
  add(base);
  return {
    lang,
    add,
    t(key, vars = {}) {
      const text = tables[lang]?.[key];
      // Invariant: every UI string exists in the app's language — a missing key
      // would show "undefined" to users; fail loudly so the gate catches it.
      if (text === undefined) throw new Error(`Missing UI string "${key}" for language "${lang}"`);
      return text.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k]));
    },
  };
}
