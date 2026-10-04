/*
  ui/support.ts — the "support the author" link (Buy Me a Coffee by default).

  Defines : createSupportLink().
  Used by : platform.ts (platform.supportLink()); the app places the link
            wherever it wants — the gate only requires it to be visible.
  Uses    : core/i18n.ts, ui/dom.ts; site.json "support": { "url": "https://…" }.

  A plain link, never the provider's widget: a widget would load scripts and
  images from their servers on every visit (not local-only). A link is the
  user's own navigation, like any other link — nothing is requested until
  they click it.
*/
import type { I18n } from "../core/i18n.ts";
import { el } from "./dom.ts";

export function createSupportLink(url: string, i18n: I18n): HTMLAnchorElement {
  const cup = el("span", { textContent: "☕", ariaHidden: "true" });
  return el("a", { className: "swp-support", href: url, target: "_blank", rel: "noopener noreferrer" },
    cup, el("span", { className: "swp-support-text", textContent: i18n.t("supportLink") }),
    el("span", { className: "visually-hidden", textContent: ` ${i18n.t("newTab")}` }));
}
