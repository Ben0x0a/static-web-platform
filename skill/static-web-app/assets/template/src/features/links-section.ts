/*
  features/links-section.ts — feature "links": a foldable section with a list of links.

  Defines : renderLinksSection() (registered in main.ts under "links").
  Used by : main.ts (registry).
  Uses    : core/types.ts; static-web-platform (el, Platform).
*/
import { el, type Platform } from "static-web-platform";
import type { AppOptions, Link, LinksSection } from "../core/types.ts";
import "./links-section.css";

// A local letter badge: no icon service is contacted (principle 1).
const linkBadge = (link: Link): Element =>
  el("span", { className: "badge", textContent: (link.title[0] ?? "?").toUpperCase(), ariaHidden: "true" });

export function renderLinksSection(section: LinksSection, platform: Platform<AppOptions>): HTMLElement {
  const items = section.links.map(link => {
    const a = el("a", { href: link.url, target: "_blank", rel: "noopener noreferrer" },
      linkBadge(link), el("span", { textContent: link.title }),
      el("span", { className: "visually-hidden", textContent: ` ${platform.t("newTab")}` }));
    if (link.desc) a.title = link.desc;
    return el("li", {}, a);
  });
  const folded = platform.site.options.collapseOnMobile && matchMedia("(max-width: 640px)").matches;
  // <details>/<summary>: folding with keyboard + screen-reader support built in.
  return el("details", { className: "section", open: !folded },
    el("summary", {}, el("h2", { textContent: section.title })),
    el("ul", { className: "links" }, ...items));
}
