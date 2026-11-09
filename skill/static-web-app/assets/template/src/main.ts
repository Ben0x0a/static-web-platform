/*
  main.ts — the app layer: starts the platform, registers the features, renders
  the content. The only place that knows every feature (wiring, no logic).

  Defines : nothing exported; runs once on load.
  Used by : the bundler entry (site.json "entry").
  Uses    : static-web-platform (startPlatform, createRegistry, byId),
            core/types.ts, features/*, content.ts, app.css.

  Add a feature: write features/<name>.ts (+ .css), add its type to
  core/types.ts, register it below. Nothing else changes.
*/
import { byId, createRegistry, startPlatform, type Platform } from "static-web-platform";
import { renderLinksSection } from "./features/links-section.ts";
import { mountSearch } from "./features/search.ts";
import { CONTENT } from "./content.ts";
import type { AppOptions, Section } from "./core/types.ts";
import "./app.css";

const platform = startPlatform<AppOptions>({
  strings: {
    en: { skip: "Skip to content", search: "Filter links", results: "{n} result(s)" },
    fr: { skip: "Aller au contenu", search: "Filtrer les liens", results: "{n} résultat(s)" },
  },
});

const renderers = createRegistry<Section, HTMLElement, Platform<AppOptions>>();
renderers.register("links", renderLinksSection);

byId("app-title").textContent = platform.site.title;
byId("skip-link").textContent = platform.t("skip");
const app = byId("app");
app.replaceChildren(...CONTENT.map(section => renderers.render(section, platform)));
mountSearch(byId("search-slot"), app, platform);
// "Support the author" link (site.json "support"; remove both to drop it).
const support = platform.supportLink();
if (support) byId("app-footer").append(support);
