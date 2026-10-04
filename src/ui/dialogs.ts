/*
  ui/dialogs.ts — the platform's accessible dialogs: consent, privacy, install help.

  Defines : mountDialogs() → { askConsent, openPrivacy, openInstallHelp }.
  Used by : platform.ts.
  Uses    : ui/dom.ts, core/i18n.ts, services/consent.ts, services/storage.ts.

  Native <dialog>.showModal(): focus moves in and is trapped, Esc closes, the
  page behind is inert — accessible without extra code. Consent: initial focus
  on "Deny" (safe default); Esc = deny.
*/
import type { I18n } from "../core/i18n.ts";
import type { Consent, ConsentAnswer, ConsentQuestion, ConsentState } from "../services/consent.ts";
import { setTheme, storedTheme, type Theme } from "../services/display.ts";
import type { Shortcuts } from "../services/shortcuts.ts";
import type { PrefixedStore } from "../services/storage.ts";
import { el } from "./dom.ts";

export interface ShareItem { label: string; value: string }

export interface Dialogs {
  askConsent(question: ConsentQuestion): Promise<ConsentAnswer>;
  /** Warn, list what the link contains, copy it only after confirmation. Resolves true when copied. */
  confirmShare(link: string, items: ShareItem[]): Promise<boolean>;
  openPrivacy(): void;
  openInstallHelp(): void;
  openAccessibility(): void;
}

export interface DialogDeps {
  i18n: I18n;
  /** Set after creation: consent needs askConsent, the privacy dialog needs consent. */
  consent: () => Consent;
  stores: PrefixedStore[];
  /** The persistent store (theme choice). */
  store: PrefixedStore;
  shortcuts: Shortcuts;
  /** Offer a light / dark / system theme choice (site.json "themeSwitch"). */
  themeSwitch: boolean;
}

export function mountDialogs({ i18n, consent, stores, store, shortcuts, themeSwitch }: DialogDeps): Dialogs {
  const { t } = i18n;
  const button = (key: string, extra: Partial<HTMLButtonElement> = {}) =>
    el("button", { type: "button", textContent: t(key), ...extra });
  const labelled = (dialog: HTMLDialogElement, titleId: string, bodyId?: string) => {
    dialog.setAttribute("aria-labelledby", titleId);
    if (bodyId) dialog.setAttribute("aria-describedby", bodyId);
    return dialog;
  };

  /* ---- Consent ----
     Scope "origin": Deny / Allow for this session / Always allow.
     Scope "request": the exact value sent is shown verbatim; Deny / Send once. */
  const originText = el("dd", { id: "consent-origin" });
  const purposeText = el("dd", { id: "consent-purpose" });
  const discloseValue = el("code", { className: "consent-value" });
  const discloseRow = el("dd", {}, el("span", { textContent: t("consentSentValue") }), " ", discloseValue);
  const referrerText = el("dd");
  const answers: Record<ConsentAnswer, HTMLButtonElement> = {
    deny: button("deny", { autofocus: true }),
    once: button("once", { className: "primary" }),
    session: button("session"),
    always: button("always", { className: "primary" }),
  };
  const consentDialog = labelled(el("dialog", { id: "consent-dialog" },
    el("h2", { id: "consent-title", textContent: t("consentTitle") }),
    el("div", { id: "consent-body" },
      el("p", { textContent: t("consentIntro") }),
      el("dl", {},
        el("dt", { textContent: t("consentOrigin") }), originText,
        el("dt", { textContent: t("consentPurpose") }), purposeText,
        el("dt", { textContent: t("consentSent") }), discloseRow, el("dd", { textContent: t("consentSentText") }),
        el("dt", { textContent: t("consentReferrer") }), referrerText)),
    el("div", { className: "dialog-buttons" }, answers.deny, answers.once, answers.session, answers.always)),
    "consent-title", "consent-body");
  for (const [answer, b] of Object.entries(answers)) b.dataset.answer = answer;

  /* ---- Privacy ---- */
  const list = el("ul", { className: "origin-list", id: "privacy-list" });
  const stateLabel: Record<ConsentState, string> = {
    "always": t("stateAlways"), "session-allow": t("stateSession"),
    "session-deny": t("stateDenied"), "ask": t("stateAsk"), "per-request": t("stateRequest"),
  };
  const renderPrivacy = (): void => {
    const origins = Object.keys(consent().declared());
    list.replaceChildren(...origins.map(origin => {
      const state = consent().state(origin);
      const forget = button("forget", { disabled: state === "ask" || state === "per-request",
        onclick: () => { consent().forget(origin); renderPrivacy(); } });
      forget.setAttribute("aria-label", `${t("forget")} — ${origin}`);
      return el("li", {}, el("span", {}, el("strong", { textContent: origin }), ` — ${stateLabel[state]}`), forget);
    }));
    if (!origins.length) list.append(el("li", { textContent: "—" }));
  };
  const privacyDialog: HTMLDialogElement = labelled(el("dialog", { id: "privacy-dialog" },
    el("h2", { id: "privacy-title", textContent: t("privacy") }),
    el("p", { textContent: t("privacyIntro") }),
    list,
    el("div", { className: "dialog-buttons" },
      button("clearData", { onclick: () => {
        if (confirm(t("clearConfirm"))) { stores.forEach(s => s.clearAll()); location.reload(); }
      } }),
      button("close", { className: "primary", onclick: () => privacyDialog.close() }))),
    "privacy-title");

  /* ---- Install help ---- */
  const installDialog: HTMLDialogElement = labelled(el("dialog", { id: "install-dialog" },
    el("h2", { id: "install-title", textContent: t("installHelpTitle") }),
    el("p", { textContent: t("installHelpIntro") }),
    el("ul", {}, ...["installIos", "installMac", "installChromium", "installAndroid", "installOther"]
      .map(key => el("li", { textContent: t(key) }))),
    el("div", { className: "dialog-buttons" },
      button("close", { className: "primary", onclick: () => installDialog.close() }))),
    "install-title");

  /* ---- Share (privacy warning before anything is copied) ---- */
  const shareList = el("dl", { className: "share-items" });
  const shareManual = el("input", { id: "share-link", type: "text", readOnly: true, hidden: true });
  const shareManualLabel = el("label", { htmlFor: "share-link", textContent: t("shareManual"), hidden: true });
  const shareCancel = button("cancel", { autofocus: true });
  const shareCopy = button("shareCopy", { className: "primary" });
  shareCancel.dataset.answer = "cancel";
  shareCopy.dataset.answer = "copy";
  const shareDialog = labelled(el("dialog", { id: "share-dialog" },
    el("h2", { id: "share-title", textContent: t("shareTitle") }),
    el("div", { id: "share-body" },
      el("p", { textContent: t("shareWarning") }),
      shareList, shareManualLabel, shareManual),
    el("div", { className: "dialog-buttons" }, shareCancel, shareCopy)),
    "share-title", "share-body");

  /* ---- Accessibility: single-key shortcuts switch (WCAG 2.1.4), theme ---- */
  const shortcutsToggle = el("input", { type: "checkbox", id: "a11y-shortcuts",
    onchange: () => shortcuts.setEnabled(shortcutsToggle.checked) });
  const shortcutsList = el("ul", { id: "a11y-shortcut-list" });
  const themeChoices: Theme[] = ["system", "light", "dark"];
  const themeInputs = themeChoices.map(theme => el("input", { type: "radio", name: "a11y-theme",
    id: `a11y-theme-${theme}`, value: theme, onchange: () => setTheme(store, theme) }));
  const themeFieldset = el("fieldset", { hidden: !themeSwitch },
    el("legend", { textContent: t("themeLegend") }),
    ...themeChoices.flatMap((theme, i) => [el("div", { className: "choice" }, themeInputs[i] as HTMLInputElement,
      el("label", { htmlFor: `a11y-theme-${theme}`, textContent: t(`theme_${theme}`) }))]));
  const accessibilityDialog: HTMLDialogElement = labelled(el("dialog", { id: "accessibility-dialog" },
    el("h2", { id: "accessibility-title", textContent: t("accessibility") }),
    el("div", { className: "choice" }, shortcutsToggle,
      el("label", { htmlFor: "a11y-shortcuts", textContent: t("shortcutsToggle") })),
    el("p", { className: "hint", textContent: t("shortcutsHint") }),
    shortcutsList,
    themeFieldset,
    el("div", { className: "dialog-buttons" },
      button("close", { className: "primary", onclick: () => accessibilityDialog.close() }))),
    "accessibility-title");

  document.body.append(consentDialog, privacyDialog, installDialog, shareDialog, accessibilityDialog);

  return {
    askConsent(question) {
      // HOW: fill the dialog for this question's scope, open it modally and
      // resolve with the button pressed (Esc = deny).
      return new Promise(resolve => {
        const perRequest = question.scope === "request";
        originText.textContent = question.origin;
        purposeText.textContent = question.purpose;
        discloseValue.textContent = question.disclose ?? "";
        discloseRow.hidden = question.disclose === undefined;
        referrerText.textContent = t(question.referrer === "no-referrer" ? "referrerNone" : "referrerOrigin");
        answers.once.hidden = !perRequest;
        answers.session.hidden = perRequest;
        answers.always.hidden = perRequest;
        const done = (answer: ConsentAnswer) => { consentDialog.close(); resolve(answer); };
        for (const [answer, b] of Object.entries(answers)) b.onclick = () => done(answer as ConsentAnswer);
        consentDialog.oncancel = e => { e.preventDefault(); done("deny"); };
        consentDialog.showModal();
      });
    },
    confirmShare(link, items) {
      // HOW: list the contents, wait for an explicit "Copy link"; if the
      // clipboard is unavailable, show the link selected for manual copying.
      return new Promise(resolve => {
        shareList.replaceChildren(...items.flatMap(item =>
          [el("dt", { textContent: item.label }), el("dd", { textContent: item.value })]));
        shareManual.hidden = shareManualLabel.hidden = true;
        shareCopy.hidden = false;
        const close = (copied: boolean) => { shareDialog.close(); resolve(copied); };
        shareCancel.onclick = () => close(false);
        shareDialog.oncancel = e => { e.preventDefault(); close(false); };
        shareCopy.onclick = async () => {
          try {
            await navigator.clipboard.writeText(link);
            close(true);
          } catch {
            shareManual.value = link;
            shareManual.hidden = shareManualLabel.hidden = false;
            shareCopy.hidden = true;
            shareManual.focus();
            shareManual.select();
          }
        };
        shareDialog.showModal();
      });
    },
    openPrivacy() { renderPrivacy(); privacyDialog.showModal(); },
    openInstallHelp() { installDialog.showModal(); },
    openAccessibility() {
      const list = shortcuts.list();
      shortcutsToggle.checked = shortcuts.enabled();
      shortcutsToggle.disabled = list.length === 0;
      shortcutsList.replaceChildren(...(list.length
        ? list.map(s => el("li", {}, el("kbd", { textContent: s.key }), ` — ${s.description}`))
        : [el("li", { textContent: t("shortcutsNone") })]));
      const current = storedTheme(store);
      themeInputs.forEach(input => { input.checked = input.value === current; });
      accessibilityDialog.showModal();
    },
  };
}
