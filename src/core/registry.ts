/*
  core/registry.ts — the feature registry: one content type = one renderer
  registered under its type name. Adding a feature = one new module in the
  app's features/ + one register() call; nothing else changes (open/closed).

  Defines : createRegistry<Spec, Output, Context>().
  Used by : apps (e.g. widgets keyed by spec.type); framework apps may use
            their own component model instead.
  Uses    : nothing (pure, DOM-agnostic: Output is whatever renderers return).
*/

export interface Registry<S extends { type: string }, R, C> {
  /** Register the renderer for one spec type; registering a type twice is an error. */
  register<T extends S["type"]>(type: T, render: (spec: Extract<S, { type: T }>, ctx: C) => R): void;
  /** Render one spec with the renderer registered for its type. */
  render(spec: S, ctx: C): R;
  /** Registered type names, in registration order. */
  types(): string[];
}

export function createRegistry<S extends { type: string }, R, C>(): Registry<S, R, C> {
  const renderers = new Map<string, (spec: S, ctx: C) => R>();
  return {
    register(type, render) {
      // Invariant: one renderer per type — a second registration would
      // silently replace the first and hide a wiring mistake.
      if (renderers.has(type)) throw new Error(`Renderer for type "${type}" registered twice`);
      renderers.set(type, render as (spec: S, ctx: C) => R);
    },
    render(spec, ctx) {
      const render = renderers.get(spec.type);
      // Invariant: content only uses registered types; an unknown type is a
      // typo in the content or a missing register() call in main.
      if (!render) throw new Error(`No renderer registered for type "${spec.type}"`);
      return render(spec, ctx);
    },
    types: () => [...renderers.keys()],
  };
}
