/*
  content.ts — EDIT HERE: the app's content, typed against core/types.ts (a
  misspelt field or a missing one stops the build with its line number).

  Defines : CONTENT. Order in this file == order on screen.
  Used by : main.ts.
  Uses    : core/types.ts.
*/
import type { Section } from "./core/types.ts";

export const CONTENT: Section[] = [
  { type: "links", title: "Example", links: [
    { title: "Example link", url: "https://example.org", desc: "Optional tooltip" },
  ] },
];
