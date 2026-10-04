/*
  ui/dom.ts — tiny DOM helpers (no framework).

  Defines : el() (create + assign properties + append), byId() (lookup that
            throws when the page contract is broken).
  Used by : ui/dialogs.ts, ui/actions.ts; apps without a framework (index.ts).
  Uses    : the DOM.
*/

/** Create an element, assign its DOM properties, append children. */
export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<HTMLElementTagNameMap[K]> = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

/** Element by id. Throws when missing: ids used with it are part of the page contract. */
export function byId<T extends HTMLElement = HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  // Invariant: the id exists in index.html or was created by the platform;
  // a missing one is a broken page shell, not a runtime condition.
  if (!node) throw new Error(`Missing element #${id}`);
  return node as T;
}
