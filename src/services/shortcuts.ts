/*
  services/shortcuts.ts — single-key keyboard shortcuts that users can turn off (WCAG 2.1.4).

  Defines : createShortcuts() → { add, list, enabled, setEnabled }.
  Used by : platform.ts (platform.shortcuts), ui/dialogs.ts (Accessibility dialog).
  Uses    : services/storage.ts ("shortcuts" = "off" when disabled).

  WHY: speech-input users can trigger single-character shortcuts by accident
  (a dictated word containing "/" jumps focus). Every single-key shortcut of
  an app goes through here, so one switch turns them all off; the gate
  fails when an app reacts to single keys on its own.
  Shortcuts never fire while typing (inputs, editable areas), with a modifier
  key held, or while a dialog is open.
*/
import type { PrefixedStore } from "./storage.ts";

export interface Shortcut {
  /** The key, as KeyboardEvent.key ("/", "?", "n"…). */
  key: string;
  /** Shown in the Accessibility dialog. */
  description: string;
  run(): void;
}

export interface Shortcuts {
  add(shortcut: Shortcut): void;
  list(): Shortcut[];
  enabled(): boolean;
  setEnabled(on: boolean): void;
}

const STORE_KEY = "shortcuts";

const isTyping = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement
  && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

export function createShortcuts(store: PrefixedStore): Shortcuts {
  const registered = new Map<string, Shortcut>();
  const enabled = () => store.get(STORE_KEY) !== "off";
  document.addEventListener("keydown", event => {
    if (!enabled() || event.ctrlKey || event.metaKey || event.altKey || isTyping(event.target)
        || document.querySelector("dialog[open]")) return;
    const shortcut = registered.get(event.key);
    if (!shortcut) return;
    event.preventDefault();
    shortcut.run();
  });
  return {
    add(shortcut) {
      // Invariant: one action per key — a second registration would silently
      // replace the first and make the Accessibility list wrong.
      if (registered.has(shortcut.key)) throw new Error(`Shortcut "${shortcut.key}" registered twice`);
      registered.set(shortcut.key, shortcut);
    },
    list: () => [...registered.values()],
    enabled,
    setEnabled(on) { if (on) store.del(STORE_KEY); else store.set(STORE_KEY, "off"); },
  };
}
