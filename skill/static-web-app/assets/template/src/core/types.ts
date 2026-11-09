/*
  core/types.ts — the app's data model (pure: no DOM, no platform).

  Defines : Link, Section (content shape), AppOptions (site.json "options").
  Used by : content.ts (typed against it), features/*, main.ts, tests.
  Uses    : nothing.
*/

export interface Link {
  title: string;
  url: string;
  /** Tooltip text. */
  desc?: string;
}

/** One content block; `type` selects the feature that renders it. */
export interface LinksSection {
  type: "links";
  title: string;
  links: Link[];
}

export type Section = LinksSection;

export interface AppOptions {
  collapseOnMobile: boolean;
}
