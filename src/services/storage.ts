/*
  services/storage.ts — browser storage that is prefixed per app and never throws.

  Defines : PrefixedStore, createStore().
  Used by : platform.ts (store / sessionStore for the platform and the apps).
  Uses    : the browser's localStorage / sessionStorage.

  WHY the prefix: pages opened from file:// can share one storage area, so
  two local apps would otherwise overwrite each other's keys.
  WHY never throw: storage is unavailable in private windows or with blocked
  site data; the app must keep working, only without memory.
*/

export interface PrefixedStore {
  get(key: string): string | null;
  set(key: string, value: string): void;
  del(key: string): void;
  /** Remove every key of this app (this prefix) — "Clear all local data". */
  clearAll(): void;
}

export function createStore(prefix: string, area: () => Storage): PrefixedStore {
  const full = (key: string) => `${prefix}:${key}`;
  return {
    get(key) { try { return area().getItem(full(key)); } catch { return null; } },
    set(key, value) { try { area().setItem(full(key), value); } catch { /* storage unavailable */ } },
    del(key) { try { area().removeItem(full(key)); } catch { /* storage unavailable */ } },
    clearAll() {
      try {
        const storage = area();
        Object.keys(storage).filter(k => k.startsWith(`${prefix}:`)).forEach(k => storage.removeItem(k));
      } catch { /* storage unavailable */ }
    },
  };
}
