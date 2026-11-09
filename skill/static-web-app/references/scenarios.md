# Scenarios (`scenarios.json`)

The gate checks the first screen by itself. Everything reached **by interaction**
(results shown, panels opened, dialogs, each mode, an answer revealed) is only checked
if the app describes how to get there. Contrast, target size and focus problems
often appear only after interaction.

The file is required at the app root. `{"scenarios": []}` is allowed, but must be a
deliberate choice (a single-screen app).

## Format

```json
{
  "scenarios": [
    { "name": "search with results",
      "steps": [ { "click": "#search" }, { "fill": ["#search", "example"] }, { "expect": "text=Example result" } ] },
    { "name": "evidence panel", "devices": ["desktop"],
      "steps": [ { "click": "text=Show evidence" }, { "expect": "#evidence[open]" } ] },
    { "name": "hash lookup asks every time with the value",
      "steps": [ { "fill": ["#hash", "d41d8cd98f00b204e9800998ecf8427e"] }, { "click": "#lookup" },
                 { "expect": "#consent-dialog .consent-value >> text=d41d8cd98f00b204e9800998ecf8427e" },
                 { "consent": "deny" } ] }
  ]
}
```

| Step | Does |
|---|---|
| `{"click": selector}` | click (Playwright selector: CSS, `text=…`, `>>` chains) |
| `{"fill": [selector, text]}` | type into a field; the text is then checked against the URL and the title |
| `{"press": key}` | a key on the focused element (`"Enter"`, `"End"`, `"Shift+Tab"`) |
| `{"expect": selector}` | wait until visible (fails the scenario otherwise) |
| `{"wait": ms}` | pause (avoid; prefer `expect`) |
| `{"upload": [selector, "tests/fixtures/file"]}` | choose a file in an `<input type="file">`; the file must be under `tests/fixtures/` (**small, synthetic** — never real evidence) |
| `{"consent": "deny"\|"once"\|"session"\|"always"}` | answer the open consent dialog; requests to that origin are then allowed for the rest of the scenario (except after `deny`). **`once` exists only for `"scope": "request"` origins; `session`/`always` only for the others** — a wrong answer fails at once with the answers offered |

`"devices"` defaults to `["desktop", "phone"]` (390×844, touch). Each scenario starts
from a fresh page.

## What the gate checks after each scenario
- axe-core WCAG A/AA (plus label-in-name), real `<label>`s;
- keyboard walk: reachable, visible focus, no trap, focus never hidden under a
  sticky header (Tab and Shift+Tab; elements tracked by identity);
- no data in the URL, and nothing typed (`fill`) in the URL or the page title;
- no request without consent; no console errors;
- on phones: zoom allowed, fields ≥ 16px and ≥ 44px tall, targets ≥ 44×44px.

## What to cover
- every screen state a user can reach: results / no results, each panel or details
  opened, each dialog of the app, each mode of a multi-mode app;
- every consent path: the dialog shows the right value (`expect` on
  `.consent-value`), then `deny`, and the app degrades cleanly;
- the share dialog (`expect` `#share-dialog`); its warning is part of the screen
  checked;
- import screens: `upload` a synthetic fixture, then `expect` the result;
- popovers and menus: open them and leave them open; the accessibility scan runs
  before the keyboard walk (which may close them). The walk always starts from the top
  of the page (or of an open dialog), not from where the scenario left focus, and it
  copes with elements that disappear;
- on phones: folded sections opened, menus opened.

Keep each scenario short and named after what the user does. One scenario per screen
state is better than a long one: a failing step stops only its own scenario.
