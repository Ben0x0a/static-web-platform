"""gate.py — the verification gate (`swp gate`): run before reporting done or shipping.

Defines : run_gate() and the checks below.
          Build   : public/ up to date; fresh build into a temporary folder
                    pointed (--site-url) at a local test server.
          Screens : the first screen, then every app scenario (scenarios.json),
                    on desktop and phone. On each: axe-core WCAG A/AA (+ label
                    in name), real <label>s, keyboard walk (all reachable,
                    focus visible, focus cycles = no trap; on phones focus
                    not hidden under a sticky header), no data in the URL,
                    nothing typed appearing in the URL or title, no request
                    without consent, no console errors; on phones: zoom
                    allowed, fields ≥ 16px, tap targets ≥ 44px.
          Once    : CSP checks, reflow 320/390px and landscape, text spacing
                    (WCAG 1.4.12), single keys inert when shortcuts are off
                    (2.1.4), focus visible in forced colours, offline reload,
                    privacy/accessibility/install dialogs scanned.
          Single  : self-contained, no request on open, CSP, axe, labels,
                    mobile, keyboard, update check asks consent first →
                    "up to date" → "new version" after version.json changes.
Used by : cli.py (`swp gate`), CI.
Uses    : builder.py, config.py, serve.py; the app's scenarios.json;
          Playwright driving the installed Google Chrome; axe-core (pinned,
          SHA-256 verified, cached in ~/.cache, test-time only — never shipped).
"""

import dataclasses
import enum
import hashlib
import json
import logging
import pathlib
import re
import tempfile
import threading
import urllib.request

from playwright.sync_api import Page, sync_playwright

from swp_tools.builder import build, check
from swp_tools.config import load_project
from swp_tools.serve import make_server

_LOG = logging.getLogger("swp.gate")

AXE_VERSION = "4.13.0"
AXE_SHA256 = "c24f097bd2f451d4f933e8bc7d8d539f8672a2ebcb5cc9f9f3eec8ca9470a0c1"
AXE_URL = f"https://cdn.jsdelivr.net/npm/axe-core@{AXE_VERSION}/axe.min.js"
AXE_CACHE_PATH = pathlib.Path.home() / ".cache" / "static-web-platform" / f"axe-{AXE_VERSION}.min.js"
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]
REFLOW_WIDTHS = (320, 390)
DESKTOP = {"width": 1280, "height": 900}
PHONE = {"width": 390, "height": 844}
PHONE_LANDSCAPE = {"width": 844, "height": 390}
MIN_TAP_PX = 44                # house rule on phones (WCAG 2.2 AA minimum is 24)
MIN_FIELD_FONT_PX = 16         # below this, iOS Safari zooms the page on focus
SCENARIOS_FILENAME = "scenarios.json"
STEP_KINDS = {"click", "fill", "press", "expect", "wait", "consent", "upload"}
FIXTURES_DIR = "tests/fixtures"     # scenario uploads: small, synthetic files only
CONSENT_ANSWERS = {"deny", "once", "session", "always"}
SHORTCUT_PROBE_KEYS = list("abcdefghijklmnopqrstuvwxyz0123456789") + ["/", "?", ".", ","]

# Shared page-side helpers, installed before each check that needs them.
PAGE_HELPERS_JS = """() => {
  window.__swpDescribe = e => e.id ? '#' + e.id
    : e.tagName.toLowerCase() + ' "' + (e.textContent || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 30) + '"';
  // Stable identity per element: the tab order can change during a walk
  // (popovers opening/closing), so positions in the list are not identities.
  window.__swpIdMap = window.__swpIdMap || new WeakMap();
  window.__swpNextId = window.__swpNextId || 1;
  window.__swpId = e => { if (!window.__swpIdMap.has(e)) window.__swpIdMap.set(e, window.__swpNextId++); return window.__swpIdMap.get(e); };
  window.__swpTabbable = () => [...document.querySelectorAll(
      'a[href], button, input:not([type=hidden]), select, textarea, summary, [tabindex], [contenteditable="true"]')]
    .filter(e => e.tabIndex >= 0 && !e.disabled && !e.closest('[inert]')
      // checkVisibility(): also false inside a closed <details> (content-visibility: hidden).
      && e.checkVisibility({ visibilityProperty: true, contentVisibilityAuto: true })
      && !e.closest('dialog:not([open])')
      && (!document.querySelector('dialog[open]') || e.closest('dialog[open]')))
    // A radio group is ONE tab stop (arrow keys move inside): keep the checked
    // radio, or the first one of the group when none is checked.
    .filter((e, _, all) => e.type !== 'radio' || !e.name || e === (
      all.find(r => r.type === 'radio' && r.name === e.name && r.checked)
      ?? all.find(r => r.type === 'radio' && r.name === e.name)));
}"""

TAP_TARGETS_JS = """([minSize]) => {
  const selector = 'a[href], button, input:not([type=hidden]), select, textarea, summary, '
                 + '[role="tab"], [tabindex]:not([tabindex="-1"])';
  return [...document.querySelectorAll(selector)].flatMap(e => {
    if (e.closest('dialog:not([open])') || !e.checkVisibility({ visibilityProperty: true })) return [];
    const r = e.getBoundingClientRect();
    const style = getComputedStyle(e);
    if (!r.width || !r.height || r.bottom <= 0 || r.right <= 0 || style.visibility === 'hidden') return [];
    // WCAG 2.5.8 exception: a link inside a sentence is sized by the text around it.
    if (e.tagName === 'A' && style.display === 'inline') return [];
    // Only VISIBLE boxes count (an invisible enlarged hit area does not) — but a
    // field's own visible <label> is part of its target: clicking it activates
    // the field, so a normal-size checkbox in a 44px label row passes.
    let box = { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
    for (const l of (e.labels || [])) {
      const lr = l.getBoundingClientRect();
      if (!lr.width || !lr.height) continue;
      box = { left: Math.min(box.left, lr.left), top: Math.min(box.top, lr.top),
              right: Math.max(box.right, lr.right), bottom: Math.max(box.bottom, lr.bottom) };
    }
    const w = box.right - box.left, h = box.bottom - box.top;
    return (w < minSize || h < minSize) ? [`${window.__swpDescribe(e)} ${Math.round(w)}×${Math.round(h)}`] : [];
  });
}"""

FOCUS_STATE_JS = """([checkObscured]) => {
  const e = document.activeElement;
  if (!e || e === document.body) return { index: -1 };
  const style = getComputedStyle(e);
  const visible = (style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2) || style.boxShadow !== 'none';
  let obscured = false;
  if (checkObscured) {
    const r = e.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + Math.min(r.width / 2, 20), r.top + Math.min(r.height / 2, 10));
    obscured = !hit || !(hit === e || e.contains(hit) || hit.contains(e));
  }
  return { index: window.__swpTabbable().includes(e) ? window.__swpId(e) : -1, name: window.__swpDescribe(e), visible, obscured };
}"""

TEXT_SPACING_JS = """() => {
  // WCAG 1.4.12 values, applied through the CSSOM (allowed by the strict CSP).
  for (const e of document.querySelectorAll('body *')) {
    e.style.setProperty('line-height', '1.5', 'important');
    e.style.setProperty('letter-spacing', '0.12em', 'important');
    e.style.setProperty('word-spacing', '0.16em', 'important');
  }
  for (const p of document.querySelectorAll('p')) p.style.setProperty('margin-bottom', '2em', 'important');
  const clipped = [...document.querySelectorAll('body *')].filter(e => {
    const s = getComputedStyle(e);
    if (!e.textContent.trim() || e.clientWidth <= 2 || e.closest('dialog:not([open])')) return false;
    const hides = ['hidden', 'clip'].includes(s.overflowX) || ['hidden', 'clip'].includes(s.overflowY);
    return hides && (e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1)
      && s.textOverflow !== 'ellipsis' && !e.classList.contains('visually-hidden');
  }).map(e => window.__swpDescribe(e));
  const overflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  return { clipped: clipped.slice(0, 8), overflow };
}"""


class Status(enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclasses.dataclass
class Report:
    rows: list[tuple[Status, str, str]] = dataclasses.field(default_factory=list)  # mutable default — shared across instances if = [] were used

    def add(self, status: Status, name: str, detail: str = "") -> None:
        self.rows.append((status, name, detail))

    def check(self, ok: bool, name: str, detail: str = "") -> bool:
        self.add(Status.PASS if ok else Status.FAIL, name, "" if ok else detail)
        return ok

    @property
    def failed(self) -> bool:
        return any(s is Status.FAIL for s, _, _ in self.rows)


@dataclasses.dataclass
class Watch:
    """External requests and console errors of one page; origins the scenario granted."""
    own_origin: str | None
    external: list[str] = dataclasses.field(default_factory=list)  # mutable default — shared across instances if = [] were used
    errors: list[str] = dataclasses.field(default_factory=list)    # mutable default — shared across instances if = [] were used
    granted: set[str] = dataclasses.field(default_factory=set)     # mutable default — shared across instances if = set() were used

    def unconsented(self) -> list[str]:
        return [u for u in self.external if not any(u.startswith(o + "/") for o in self.granted)]


def load_axe() -> str:
    """axe-core's source, downloaded once and verified against its SHA-256."""
    if not AXE_CACHE_PATH.is_file():
        AXE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOG.info(f"Downloading axe-core {AXE_VERSION} (test-time only, never shipped)")
        AXE_CACHE_PATH.write_bytes(urllib.request.urlopen(AXE_URL, timeout=30).read())
    data = AXE_CACHE_PATH.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    # A mismatch means a corrupted cache or a tampered CDN file: never run it.
    if digest != AXE_SHA256:
        AXE_CACHE_PATH.unlink()
        raise RuntimeError(f"axe-core SHA-256 mismatch ({digest}); cache deleted")
    return data.decode("utf-8")


def load_scenarios(root: pathlib.Path) -> list[dict]:
    """The app's scenarios.json (required; an empty list is allowed but must be explicit)."""
    path = root / SCENARIOS_FILENAME
    if not path.is_file():
        raise SystemExit(f"{path} missing: list the screens reached by interaction (\"scenarios\": [] if none)")
    scenarios = json.loads(path.read_text(encoding="utf-8")).get("scenarios")
    if not isinstance(scenarios, list):
        raise SystemExit(f"{path}: expected {{\"scenarios\": [...]}}")
    for scenario in scenarios:
        for step in scenario.get("steps", []):
            kinds = set(step) & STEP_KINDS
            # Invariant: one action per step, from the documented set — an
            # unknown key would otherwise be silently skipped.
            if len(step) != 1 or not kinds:
                raise SystemExit(f"{path}: scenario '{scenario.get('name')}': invalid step {step} "
                                 f"(one of {sorted(STEP_KINDS)})")
            if "consent" in step and step["consent"] not in CONSENT_ANSWERS:
                raise SystemExit(f"{path}: consent answer must be one of {sorted(CONSENT_ANSWERS)}")
            if "upload" in step:
                selector, file_name = step["upload"]
                fixture = (root / file_name).resolve()
                # Invariant: uploads come from tests/fixtures/ (small, synthetic,
                # committed) — never a real evidence file from somewhere else.
                if not fixture.is_relative_to((root / FIXTURES_DIR).resolve()) or not fixture.is_file():
                    raise SystemExit(f"{path}: upload {file_name}: must be an existing file under {FIXTURES_DIR}/")
    return scenarios


def watch_page(page: Page, own_origin: str | None) -> Watch:
    watch = Watch(own_origin)

    def on_request(req):
        url = req.url
        if url.startswith(("http://", "https://")) and not (own_origin and url.startswith(own_origin + "/")):
            watch.external.append(url)

    page.on("request", on_request)
    page.on("console", lambda m: watch.errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: watch.errors.append(f"pageerror: {e}"))
    return watch


def check_declarations(page: Page, report: Report, label: str, allowed_extra: set) -> dict:
    info = page.evaluate("""() => {
        const meta = document.querySelector('meta[http-equiv="Content-Security-Policy"]');
        const net = window.__SWP_SITE__?.netOrigins ?? null;
        return { csp: meta ? meta.content : null,
                 net: net && Object.fromEntries(Object.entries(net).map(([o, d]) => [o, d.directive])) };
    }""")
    if not report.check(info["csp"] is not None, f"{label}: CSP <meta> present", "no Content-Security-Policy meta tag"):
        return {}
    if not report.check(info["net"] is not None, f"{label}: external origins declared", "no window.__SWP_SITE__.netOrigins"):
        return {}
    csp = {tokens[0]: tokens[1:] for tokens in (p.split() for p in info["csp"].split(";")) if tokens}
    in_csp = {(o.rstrip("/"), d) for d, srcs in csp.items() for o in srcs if re.match(r"^https?://", o)}
    declared = {(o.rstrip("/"), d) for o, d in info["net"].items()}
    problems = [f"{o} declared for {d} but not in the CSP" for o, d in declared - in_csp]
    problems += [f"{o} allowed by CSP {d} but not declared" for o, d in in_csp - declared - allowed_extra]
    report.check(not problems, f"{label}: CSP ↔ declared origins consistent", "; ".join(problems))
    return csp


def run_axe(page: Page, axe_src: str, report: Report, label: str) -> None:
    if not page.evaluate("typeof axe !== 'undefined'"):
        # Inject through the DevTools protocol, which the page's CSP does not
        # govern: a <script> tag would be (rightly) blocked by a strict CSP.
        page.evaluate(f"(() => {{ {axe_src}\n; window.axe = axe; }})()")
    violations = page.evaluate("""async tags => {
        const r = await axe.run(document, { runOnly: { type: "tag", values: tags },
            // Voice control (WCAG 2.5.3): the spoken name must contain the visible text.
            rules: { "label-content-name-mismatch": { enabled: true } } });
        return r.violations.map(v => `${v.id} [${v.impact}] ${v.help} → ` +
            v.nodes.slice(0, 3).map(n => n.target.join(" ")).join(" | "));
    }""", WCAG_TAGS)
    report.check(not violations, f"axe WCAG A/AA — {label}", "\n      ".join(violations))


def check_labels(page: Page, report: Report, label: str) -> None:
    """Stricter than axe: every form field has a real <label> (a placeholder is not one)."""
    unlabelled = page.evaluate("""() => [...document.querySelectorAll('input, select, textarea')]
        .filter(f => f.type !== 'hidden' && !f.hidden && !f.closest('dialog:not([open])'))
        .filter(f => !(f.labels && f.labels.length) && !f.getAttribute('aria-labelledby'))
        .map(f => f.id ? '#' + f.id : f.outerHTML.slice(0, 60))""")
    report.check(not unlabelled, f"{label}: every form field has a <label>", ", ".join(unlabelled))


def check_keyboard(page: Page, report: Report, label: str, phone: bool, limit_stops: int | None = None) -> None:
    """Tab through the page: all reachable, focus visible, focus cycles back (no
    trap), focused element never hidden (e.g. under a sticky header) — desktop
    and phone. Elements are tracked by identity, so popovers that open or close
    during the walk do not confuse it; "reachable" is judged on the elements
    still focusable at the end."""
    page.evaluate(PAGE_HELPERS_JS)
    total = page.evaluate("window.__swpTabbable().length")
    if not total:
        report.add(Status.SKIP, f"{label}: keyboard walk", "nothing focusable")
        return
    page.evaluate("document.activeElement && document.activeElement.blur()")
    visited: set[int] = set()
    invisible: list[str] = []
    obscured: list[str] = []
    first: int | None = None
    cycled = False
    stops = limit_stops or total * 2 + 10
    for _ in range(stops):
        page.keyboard.press("Tab")
        state = page.evaluate(FOCUS_STATE_JS, [True])
        index = state["index"]
        if index < 0:
            continue                                  # browser UI / body between cycles
        if first is None:
            first = index
        elif index == first:
            cycled = True
            break
        visited.add(index)
        if not state["visible"]:
            invisible.append(state["name"])
        if state["obscured"]:
            obscured.append(state["name"])
    if limit_stops is None:
        missing = page.evaluate("ids => window.__swpTabbable().filter(e => !ids.includes(window.__swpId(e))).map(window.__swpDescribe)",
                                sorted(visited | ({first} if first is not None else set())))
        report.check(cycled, f"{label}: keyboard focus cycles (no trap)", f"focus did not come back after {stops} Tab presses")
        report.check(not missing, f"{label}: everything reachable by keyboard", ", ".join(missing[:10]))
    if True:
        # Backwards (Shift+Tab) the browser scrolls each element in at the TOP of
        # the screen — exactly where a sticky header can hide it (WCAG 2.4.11).
        for _ in range(min(total, 60)):
            page.keyboard.press("Shift+Tab")
            state = page.evaluate(FOCUS_STATE_JS, [True])
            if state["index"] >= 0 and state["obscured"]:
                obscured.append(state["name"])
    page.evaluate("document.activeElement && document.activeElement.blur()")   # leave the page as found
    report.check(not invisible, f"{label}: focus always visible", ", ".join(invisible[:10]))
    report.check(not obscured, f"{label}: focused element never hidden (WCAG 2.4.11)",
                 ", ".join(sorted(set(obscured))[:10]))


def check_url_and_title(page: Page, report: Report, label: str, typed: list[str]) -> None:
    """No data in the address bar; nothing the user typed in the URL or the title."""
    info = page.evaluate("""() => ({ search: location.search, hash: location.hash, href: location.href,
        title: document.title,
        anchor: location.hash.length > 1 && !!document.getElementById(decodeURIComponent(location.hash.slice(1))) })""")
    problems = []
    if info["search"]:
        problems.append(f"query string in the URL: {info['search'][:60]}")
    if info["hash"] and not info["anchor"]:
        problems.append(f"data in the URL fragment: {info['hash'][:60]}")
    for value in (v for v in typed if len(v) >= 2):
        if value in info["href"] or urllib.request.quote(value) in info["href"]:
            problems.append(f"typed value {value!r} appears in the URL")
        if value in info["title"]:
            problems.append(f"typed value {value!r} appears in the page title")
    report.check(not problems, f"{label}: no data in the URL or title", "; ".join(problems))


def check_phone_rules(page: Page, report: Report, label: str) -> None:
    """Phone rules every app must meet: viewport, field text size, tap targets (current viewport)."""
    page.evaluate(PAGE_HELPERS_JS)
    viewport = page.evaluate("document.querySelector('meta[name=viewport]')?.content ?? ''")
    max_scale = re.search(r"maximum-scale\s*=\s*([\d.]+)", viewport)
    blocks_zoom = bool(re.search(r"user-scalable\s*=\s*(no|0)", viewport)) or (max_scale and float(max_scale.group(1)) < 2)
    report.check("width=device-width" in viewport and not blocks_zoom, f"{label}: viewport set, zoom allowed",
                 f'viewport "{viewport}"')
    small_fields = page.evaluate("""min => [...document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea')]
        .filter(f => f.getClientRects().length && !f.closest('dialog:not([open])') && parseFloat(getComputedStyle(f).fontSize) < min)
        .map(f => (f.id ? '#' + f.id : f.tagName) + ' ' + getComputedStyle(f).fontSize)""", MIN_FIELD_FONT_PX)
    report.check(not small_fields, f"{label}: form fields ≥ {MIN_FIELD_FONT_PX}px (no iOS zoom)", ", ".join(small_fields))
    small_targets = page.evaluate(TAP_TARGETS_JS, [MIN_TAP_PX])
    report.check(not small_targets, f"{label}: tap targets ≥ {MIN_TAP_PX}×{MIN_TAP_PX}px", ", ".join(small_targets[:12]))


def check_reflow(page: Page, report: Report, label: str) -> None:
    for size in [{"width": w, "height": 800} for w in REFLOW_WIDTHS] + [PHONE_LANDSCAPE]:
        page.set_viewport_size(size)
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        report.check(overflow <= 0, f"{label}: no horizontal scroll at {size['width']}×{size['height']}",
                     f"overflows by {overflow}px")
    page.set_viewport_size(DESKTOP)


def check_text_spacing(page: Page, report: Report, label: str) -> None:
    page.evaluate(PAGE_HELPERS_JS)
    result = page.evaluate(TEXT_SPACING_JS)
    problems = ([f"horizontal overflow {result['overflow']}px"] if result["overflow"] > 0 else []) + \
               [f"clipped: {c}" for c in result["clipped"]]
    report.check(not problems, f"{label}: text spacing (WCAG 1.4.12) loses nothing", "; ".join(problems))


def check_single_keys_inert(page: Page, report: Report, label: str) -> None:
    """With shortcuts switched off, single keys must change nothing (WCAG 2.1.4)."""
    site_id = page.evaluate("window.__SWP_SITE__.id")
    page.evaluate("id => localStorage.setItem(id + ':shortcuts', 'off')", site_id)
    page.reload()
    page.wait_for_load_state("networkidle")
    page.evaluate("""() => {
        document.activeElement && document.activeElement.blur();
        window.__swpMutations = 0;
        new MutationObserver(list => { window.__swpMutations += list.length; })
            .observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
    }""")
    reacting = []
    for key in SHORTCUT_PROBE_KEYS:
        before = page.evaluate("[location.href, document.activeElement === document.body, window.__swpMutations]")
        page.keyboard.press(key)
        after = page.evaluate("[location.href, document.activeElement === document.body, window.__swpMutations]")
        if before != after:
            reacting.append(key)
            page.evaluate("document.activeElement && document.activeElement.blur()")
    page.evaluate("id => localStorage.removeItem(id + ':shortcuts')", site_id)
    report.check(not reacting, f"{label}: single keys inert when shortcuts are off (WCAG 2.1.4)",
                 f"keys still acting: {' '.join(reacting)} — use platform.shortcuts")


def settle_consent(page: Page, watch: Watch, axe_src: str, report: Report, label: str) -> None:
    """If the app asks for consent on open, verify it came first, scan it, then DENY (Esc)."""
    page.wait_for_timeout(300)
    if not page.evaluate("document.getElementById('consent-dialog')?.open === true"):
        return
    report.check(not watch.external, f"{label}: consent asked BEFORE any request", ", ".join(watch.external))
    run_axe(page, axe_src, report, f"{label}: consent dialog open")
    page.keyboard.press("Escape")
    page.wait_for_function("document.getElementById('consent-dialog')?.open !== true", timeout=5000)


def run_steps(page: Page, steps: list[dict], watch: Watch, root: pathlib.Path) -> list[str]:
    """Play a scenario; returns the values typed (checked against URL and title)."""
    typed: list[str] = []
    for step in steps:
        kind, value = next(iter(step.items()))
        if kind == "click":
            page.click(value, timeout=5000)
        elif kind == "fill":
            page.fill(value[0], value[1], timeout=5000)
            typed.append(value[1])
        elif kind == "press":
            page.keyboard.press(value)
        elif kind == "expect":
            page.wait_for_selector(value, state="visible", timeout=5000)
        elif kind == "wait":
            page.wait_for_timeout(int(value))
        elif kind == "upload":
            page.set_input_files(value[0], str(root / value[1]), timeout=5000)
        elif kind == "consent":
            page.wait_for_function("document.getElementById('consent-dialog')?.open === true", timeout=5000)
            origin = page.inner_text("#consent-origin").strip()
            offered = page.evaluate("""() => [...document.querySelectorAll('#consent-dialog [data-answer]')]
                .filter(b => !b.hidden).map(b => b.dataset.answer)""")
            if value not in offered:
                raise RuntimeError(f"consent '{value}' is not offered for {origin} (offered: {', '.join(offered)}; "
                                   "'once' exists only for \"scope\": \"request\" origins)")
            if value != "deny":
                watch.granted.add(origin)
            page.click(f"#consent-dialog [data-answer='{value}']")
        page.wait_for_timeout(150)
    return typed


def check_support_link(page: Page, report: Report, label: str) -> None:
    """When site.json declares "support", the link must be on the page and visible."""
    url = page.evaluate("window.__SWP_SITE__?.support?.url ?? null")
    if not url:
        return
    visible = page.evaluate("""url => [...document.querySelectorAll('a')].some(a => a.href === url
        && a.checkVisibility({ visibilityProperty: true }) && a.getBoundingClientRect().width > 0)""", url)
    report.check(visible, f"{label}: support link visible", f"no visible link to {url} — place platform.supportLink()")


def check_screen(page: Page, watch: Watch, axe_src: str, report: Report, label: str, phone: bool,
                 typed: list[str]) -> None:
    run_axe(page, axe_src, report, label)
    check_labels(page, report, label)
    check_keyboard(page, report, label, phone)
    check_url_and_title(page, report, label, typed)
    if phone:
        check_phone_rules(page, report, label)
    report.check(not watch.unconsented(), f"{label}: no request without consent", ", ".join(watch.unconsented()))
    report.check(not watch.errors, f"{label}: no console errors", "\n      ".join(watch.errors))


def check_offline(page: Page, context, report: Report) -> None:
    if not page.evaluate("'serviceWorker' in navigator && navigator.serviceWorker.getRegistration().then(r => !!r)"):
        report.add(Status.SKIP, "site: offline reload", "no service worker registered")
        return
    page.evaluate("navigator.serviceWorker.ready.then(() => true)")
    page.reload()                                    # now controlled by the worker
    context.set_offline(True)
    try:
        page.reload()
        report.check(len(page.inner_text("body").strip()) > 0, "site: offline reload (service worker)", "blank page offline")
    finally:
        context.set_offline(False)


def check_single_file(page: Page, context, site_dir: pathlib.Path, origin: str, work: pathlib.Path,
                      axe_src: str, report: Report) -> None:
    with page.expect_download() as info:
        page.click("#download")
    copy = work / "copy.download.html"
    info.value.save_as(copy)
    html = copy.read_text(encoding="utf-8")
    external_refs = re.findall(r'<(?:script[^>]+src|link[^>]+rel="(?:stylesheet|manifest|apple-touch-icon)")[^>]*>', html)
    report.check(not external_refs, "single file: self-contained", ", ".join(external_refs))

    local = context.new_page()
    watch = watch_page(local, None)
    local.goto(copy.as_uri())
    local.wait_for_timeout(800)
    report.check(not watch.external, "single file: no request on open", ", ".join(watch.external))
    settle_consent(local, watch, axe_src, report, "single file")
    check_declarations(local, report, "single file", allowed_extra={(origin, "connect-src")})
    check_screen(local, watch, axe_src, report, "single file desktop", phone=False, typed=[])
    check_support_link(local, report, "single file")
    local.set_viewport_size(PHONE)
    check_phone_rules(local, report, "single file phone")
    local.set_viewport_size(DESKTOP)

    if local.locator("#check-update").count() == 0:
        report.add(Status.SKIP, "single file: update check", "no #check-update")
    else:
        t = lambda key: local.evaluate("k => window.__swpT?.(k) ?? null", key)  # noqa: E731
        local.click("#check-update")
        local.wait_for_function("document.getElementById('consent-dialog')?.open === true", timeout=5000)
        report.check(not watch.external, "single file: update check asks consent BEFORE any request",
                     ", ".join(watch.external))
        local.click("#consent-dialog [data-answer='session']")
        local.wait_for_function("s => document.getElementById('status').textContent.includes(s)",
                                arg=t("upToDate"), timeout=10000)
        report.check(True, "single file: unchanged site → up to date")
        version_file = site_dir / "version.json"
        original = version_file.read_text(encoding="utf-8")
        version_file.write_text(json.dumps({**json.loads(original), "version": "simulated-new"}), encoding="utf-8")
        try:
            local.click("#check-update")
            local.wait_for_function("s => document.getElementById('status').textContent.includes(s)",
                                    arg=t("updateAvailable"), timeout=10000)
            report.check(True, "single file: new version on the site → notice shown")
        finally:
            version_file.write_text(original, encoding="utf-8")
    check_reflow(local, report, "single file")


def run_gate(root: pathlib.Path) -> Report:
    report = Report()
    axe_src = load_axe()
    project = load_project(root)
    scenarios = load_scenarios(project.root)
    report.check(check(project, project.public) == 0, "public/ is up to date with src/ (swp build)")
    with tempfile.TemporaryDirectory(prefix="swp_gate_") as tmp:
        work = pathlib.Path(tmp)
        site_dir = work / "site"
        site_dir.mkdir()
        server = make_server(site_dir)               # port known before the build
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{server.server_port}"
        try:
            build(load_project(root, site_url_override=origin + "/"), site_dir)
            report.check(True, "build succeeds (architecture + type check + bundle + assembly)")
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                contexts = {
                    "desktop": dict(viewport=DESKTOP),
                    "phone": dict(viewport=PHONE, is_mobile=True, has_touch=True, device_scale_factor=2),
                }

                # ---- First screen, desktop: everything checked once ----
                context = browser.new_context(accept_downloads=True, **contexts["desktop"])
                page = context.new_page()
                watch = watch_page(page, origin)
                page.goto(origin + "/")
                page.wait_for_load_state("networkidle")
                settle_consent(page, watch, axe_src, report, "site")
                csp = check_declarations(page, report, "site", allowed_extra=set())
                report.check("'unsafe-inline'" not in csp.get("script-src", ["'unsafe-inline'"]),
                             "site: CSP forbids inline script", f"script-src {' '.join(csp.get('script-src', []))}")
                check_screen(page, watch, axe_src, report, "site desktop", phone=False, typed=[])
                check_support_link(page, report, "site desktop")
                for opener, label in (("#privacy", "privacy dialog"), ("#accessibility", "accessibility dialog"),
                                      ("#install", "install dialog")):
                    if page.locator(opener).count() and page.is_visible(opener):
                        page.click(opener)
                        page.wait_for_timeout(200)
                        if page.evaluate("!!document.querySelector('dialog[open]')"):
                            run_axe(page, axe_src, report, f"site: {label} open")
                            check_keyboard(page, report, f"site: {label} open", phone=False)
                            page.keyboard.press("Escape")
                check_text_spacing(page, report, "site")
                page.reload()
                check_single_keys_inert(page, report, "site")
                check_offline(page, context, report)
                check_single_file(page, context, site_dir, origin, work, axe_src, report)
                check_reflow(page, report, "site")
                context.close()

                forced = browser.new_context(forced_colors="active", **contexts["desktop"]).new_page()
                forced.goto(origin + "/")
                check_keyboard(forced, report, "site forced colours", phone=False, limit_stops=15)

                # ---- First screen, phone ----
                phone_page = browser.new_context(**contexts["phone"]).new_page()
                phone_watch = watch_page(phone_page, origin)
                phone_page.goto(origin + "/")
                settle_consent(phone_page, phone_watch, axe_src, report, "site phone")
                check_screen(phone_page, phone_watch, axe_src, report, "site phone", phone=True, typed=[])
                check_support_link(phone_page, report, "site phone")

                # ---- App scenarios, desktop and phone ----
                if not scenarios:
                    report.add(Status.SKIP, "scenarios", f"{SCENARIOS_FILENAME} lists none")
                for scenario in scenarios:
                    for device in scenario.get("devices", ["desktop", "phone"]):
                        label = f"scenario '{scenario['name']}' ({device})"
                        scenario_page = browser.new_context(**contexts[device]).new_page()
                        scenario_watch = watch_page(scenario_page, origin)
                        scenario_page.goto(origin + "/")
                        scenario_page.wait_for_load_state("networkidle")
                        try:
                            typed = run_steps(scenario_page, scenario.get("steps", []), scenario_watch, project.root)
                        except Exception as err:     # a step failed: report, continue with the next scenario
                            report.check(False, f"{label}: steps play", str(err).splitlines()[0])
                            continue
                        check_screen(scenario_page, scenario_watch, axe_src, report, label,
                                     phone=device == "phone", typed=typed)
                browser.close()
        except SystemExit as err:                    # build failure: report it, do not crash
            report.check(False, "build succeeds (architecture + type check + bundle + assembly)", str(err))
        finally:
            server.shutdown()
    return report
