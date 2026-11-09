# Accessibility (WCAG 2.2 AA) — visually and motor-impaired users

The target is WCAG 2.2 level AA. `swp gate` checks a lot automatically, on the first
screen and on every app scenario, but automated checks find only part of the
problems. Every release also gets the manual pass at the end of this file.

## What the gate checks (each row fails the gate when broken)
| Check | WCAG |
|---|---|
| axe-core rules A/AA, plus **label in name** (voice control) | many; 2.5.3 |
| every form field has a real `<label>` (a placeholder is not one) | 1.3.1, 3.3.2 |
| **keyboard walk**: everything reachable, focus always visible, focus cycles (no trap) | 2.1.1, 2.1.2, 2.4.7 |
| focus **not hidden** under a sticky header (phone, Tab and Shift+Tab) | 2.4.11 |
| focus visible in **forced colours** (high contrast) | 1.4.11 |
| **text spacing** (1.5 line, 0.12em letters, 0.16em words, 2em paragraphs) loses nothing | 1.4.12 |
| no horizontal scroll at 320px, 390px, landscape | 1.4.10 |
| **single keys inert** when shortcuts are switched off | 2.1.4 |
| phones: zoom allowed; fields ≥ 16px and ≥ 44px tall; targets ≥ 44×44px (visible box) | 1.4.4, 2.5.8 |
| no data in the URL or title | (privacy) |

## Checklist

**Structure and semantics (screen readers)**
- `<html lang>` matches the UI language; passages in another language get their own
  `lang`.
- One `h1`, then `h2` per section with no skipped levels. A heading inside `<summary>`
  keeps folded sections navigable by heading.
- Landmarks: `header`, `nav` (if any), `main` (`tabindex="-1"`), `footer`. The skip
  link is the first focusable element.
- Real elements: `<button>` for actions, `<a href>` for navigation.
- Images: meaningful `alt`, or `alt=""`/`aria-hidden="true"` when decorative.
- Status messages (saved, results, up to date…) go in `role="status"`; urgent errors in
  `role="alert"`.
- Links opening a new tab carry visually hidden "(opens in a new tab)".
- `contenteditable` areas get `role="textbox"`, `aria-multiline="true"` and a label.
- **Label in name:** a control's spoken name must contain its visible text (voice
  control users say what they see).

**Low vision**
- Contrast ≥ 4.5:1 for text (≥ 3:1 for large text), ≥ 3:1 for UI, input borders and
  focus. Check every theme (`[data-theme]` light/dark, OS setting, forced colours).
- Never convey information by colour alone.
- 200% zoom and reflow at 320px; nothing clipped when text spacing is increased; no
  fixed heights on text containers.
- `prefers-reduced-motion` honoured; no flashing.
- Custom tooltips/popups (1.4.13): dismissible (Esc), hoverable (the pointer can move
  onto them), persistent (they stay until dismissed). Native `title` is fine.

**Motor and speech input**
- **Keyboard:** everything works with Tab / Shift+Tab / Enter / Space / Esc / arrows,
  in DOM order; focus is always visible; no traps; modals use
  `<dialog>.showModal()` with initial focus on the safest button.
- **Single-key shortcuts (2.1.4):** only through `platform.shortcuts.add()`. The user
  can turn them all off in *Accessibility*; they never fire while typing, with a
  modifier, or with a dialog open. Keys handled *inside* a focused widget (arrow keys
  in tabs, Esc in a field) are not global shortcuts and are fine.
- **Dragging (2.5.7):** every drag (slider, reorder, map pan, drop zone) has a
  single-pointer alternative (buttons, a file picker for drop zones).
- **Gestures (2.5.1):** no path-based or multi-finger gesture as the only way (pinch,
  swipe), so provide buttons.
- **Pointer cancellation (2.5.2):** actions trigger on release (`click`), not on
  `pointerdown`.
- **Targets (2.5.8 + house rule):** ≥ 44×44px on phones, measured on the **visible**
  box (an invisible enlarged hit area does not count); ≥ 24×24px everywhere.
- **Timing (2.2.1):** no time limit unless the user can turn it off, adjust it, or
  extend it (warning + one key/tap).
- **Focus not obscured (2.4.11):** sticky headers carry `data-swp-sticky`; the
  platform sets the scroll padding.

## Patterns
**Tabs** (notes widgets, mode switches), following the WAI-ARIA APG tabs pattern:
- `role="tablist"` (with `aria-label`) holding `<button role="tab" aria-selected
  aria-controls>`;
- the panel is `role="tabpanel" aria-labelledby`;
- roving `tabindex` (only the selected tab is 0);
- Left/Right move between tabs (wrapping) and Home/End jump to the ends.
  Keep the index arithmetic as a pure, unit-tested function in `core/`.

**Radio groups** are one tab stop; arrow keys move inside. The gate counts them that
way.

**Dialogs:** the platform's consent, privacy, accessibility, install and share
dialogs are the reference: `aria-labelledby`/`describedby`, verb labels, safe initial
focus, Esc closes.

**Visually hidden text:** `.visually-hidden` (clip pattern), never `display: none`.

## Manual pass (≈ 15 minutes per release)
1. **Keyboard only:** go through every feature and every scenario screen without the
   mouse. Check the order is logical and nothing is unreachable.
2. **VoiceOver** (macOS Cmd+F5, Safari): VO+U → Headings, then Landmarks; Tab through
   (each stop has a name and a role); use search (the count is announced); trigger a
   consent dialog (title and body read, Esc closes, focus returns); fold/unfold
   (state announced).
3. **Voice Control** (macOS: Accessibility → Voice Control): say "click Download",
   "click Privacy" and so on, using the visible words. Then "show numbers", and
   operate a feature by number. With shortcuts **on** and then **off**, dictate a word
   containing a shortcut key: nothing should fire when they're off.
4. **Zoom 400%** (Cmd + +) on a 1280px window, and a 320px-wide window: nothing cut
   off, no horizontal scroll, sticky header not covering focus.
5. **Themes and contrast:** light and dark (if `themeSwitch`), macOS "Increase
   contrast", forced colours (Windows if available).
6. **Phone:** VoiceOver (iOS) swipe navigation reaches everything; targets are easy
   to hit; install works.

Record the result (date, browser, assistive technology, issues) in the release notes
or the PR.
