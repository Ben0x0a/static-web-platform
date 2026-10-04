/*
  services/display.ts — display preferences: theme and sticky-header focus safety.

  Defines : applyStoredTheme(), setTheme(), Theme, keepFocusVisibleUnderStickyHeaders().
  Used by : platform.ts (on start), ui/dialogs.ts (theme choice in the Accessibility dialog).
  Uses    : services/storage.ts ("theme"); elements marked data-swp-sticky.

  Theme: base.css follows the OS setting unless <html data-theme="light|dark">.
  Sticky headers (WCAG 2.4.11 Focus Not Obscured): the page's scroll padding
  follows the height of every [data-swp-sticky] element, so keyboard focus
  and in-page links never end up hidden underneath it.
*/
import type { PrefixedStore } from "./storage.ts";

export type Theme = "system" | "light" | "dark";
const THEME_KEY = "theme";

export function setTheme(store: PrefixedStore, theme: Theme): void {
  if (theme === "system") {
    store.del(THEME_KEY);
    delete document.documentElement.dataset.theme;
  } else {
    store.set(THEME_KEY, theme);
    document.documentElement.dataset.theme = theme;
  }
}

export function storedTheme(store: PrefixedStore): Theme {
  const value = store.get(THEME_KEY);
  return value === "light" || value === "dark" ? value : "system";
}

export const applyStoredTheme = (store: PrefixedStore): void => setTheme(store, storedTheme(store));

export function keepFocusVisibleUnderStickyHeaders(): void {
  const sticky = [...document.querySelectorAll<HTMLElement>("[data-swp-sticky]")];
  if (!sticky.length) return;
  const update = (): void => {
    // Only elements actually stuck to the top count (sticky on phones only, for example).
    const height = Math.max(0, ...sticky
      .filter(e => ["sticky", "fixed"].includes(getComputedStyle(e).position))
      .map(e => e.getBoundingClientRect().height));
    document.documentElement.style.scrollPaddingTop = height ? `${Math.ceil(height) + 8}px` : "";
  };
  const observer = new ResizeObserver(update);
  sticky.forEach(e => observer.observe(e));
  window.addEventListener("resize", update);
  update();
}
