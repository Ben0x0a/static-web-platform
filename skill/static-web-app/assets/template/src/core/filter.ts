/*
  core/filter.ts — search matching (pure, unit-tested in tests/filter.test.ts).

  Defines : normalise(), matches().
  Used by : features/search.ts.
  Uses    : nothing.
*/

/** Lower-case and strip accents, so "cafe" finds "Café". */
export const normalise = (text: string): string =>
  text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();

/** True when every word of the query appears in one of the fields. */
export function matches(query: string, fields: string[]): boolean {
  const words = normalise(query).split(/\s+/).filter(Boolean);
  const haystack = normalise(fields.join(" "));
  return words.every(word => haystack.includes(word));
}
