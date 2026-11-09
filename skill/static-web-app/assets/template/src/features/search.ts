/*
  features/search.ts — feature "search": a labelled filter box over the rendered links.

  Defines : mountSearch().
  Used by : main.ts.
  Uses    : core/filter.ts (matching); static-web-platform (el, Platform).

  Screen readers: the input has a real <label>; the result count is announced
  through a role="status" element. Keyboard: "/" focuses it (platform
  shortcut, can be turned off), Esc clears it.
*/
import { el, type Platform } from "static-web-platform";
import { matches } from "../core/filter.ts";
import "./search.css";

export function mountSearch(slot: HTMLElement, scope: HTMLElement, platform: Platform<unknown>): void {
  const input = el("input", { id: "search", type: "search", autocomplete: "off",
                              placeholder: `${platform.t("search")}…` });
  const label = el("label", { htmlFor: "search", className: "visually-hidden", textContent: platform.t("search") });
  const status = el("span", { className: "visually-hidden" });
  status.setAttribute("role", "status");
  slot.append(label, input, status);

  // "/" focuses the search — through the platform, so users can turn it off (WCAG 2.1.4).
  platform.shortcuts.add({ key: "/", description: platform.t("search"), run: () => input.focus() });
  input.addEventListener("keydown", e => {             // scoped to the field: not a global shortcut
    if (e.key === "Escape") { input.value = ""; input.dispatchEvent(new Event("input")); }
  });
  input.addEventListener("input", () => {
    // HOW: hide non-matching links and empty sections; open sections with hits.
    let total = 0;
    scope.querySelectorAll<HTMLDetailsElement>(".section").forEach(section => {
      let visible = 0;
      section.querySelectorAll("li").forEach(li => {
        const a = li.querySelector("a");
        const hit = a !== null && matches(input.value, [a.textContent ?? "", a.href, a.title]);
        li.hidden = !hit;
        if (hit) visible++;
      });
      section.hidden = visible === 0;
      if (input.value && visible) section.open = true;
      total += visible;
    });
    status.textContent = input.value.trim() ? platform.t("results", { n: total }) : "";
  });
}
