/*
  ui/actions.ts — the platform's action bar and status line.

  Defines : mountActions() → { setStatus }.
            Site mode   : Install, Download, Privacy, status.
            Single file : Check for updates (when siteUrl is set), Privacy,
                          status "Offline copy — version X (date)".
  Used by : platform.ts.
  Uses    : ui/dom.ts, ui/dialogs.ts, core/*, services/install.ts,
            services/update.ts, services/network.ts, services/consent.ts.

  The ids (#download, #install, #check-update, #privacy, #accessibility, #status) are part of
  the platform contract: the verification gate drives them.
*/
import type { I18n } from "../core/i18n.ts";
import type { SiteConfig } from "../core/types.ts";
import { displayDate, shortVersion } from "../core/version.ts";
import type { Consent } from "../services/consent.ts";
import type { Install } from "../services/install.ts";
import type { Network } from "../services/network.ts";
import { checkForUpdate } from "../services/update.ts";
import type { Dialogs } from "./dialogs.ts";
import { el } from "./dom.ts";

export interface Actions {
  /** Replace the status line (role="status": announced to screen readers). */
  setStatus(content: string | Node, notice?: boolean): void;
}

export interface ActionDeps {
  slot: HTMLElement;
  site: SiteConfig<unknown>;
  i18n: I18n;
  dialogs: Dialogs;
  install: Install;
  net: Network;
  consent: Consent;
}

export function mountActions({ slot, site, i18n, dialogs, install, net, consent }: ActionDeps): Actions {
  const { t } = i18n;
  const status = el("span", { id: "status" });
  status.setAttribute("role", "status");
  const setStatus = (content: string | Node, notice = false): void => {
    status.replaceChildren(content);
    status.classList.toggle("notice", notice);
  };
  const privacy = el("button", { type: "button", id: "privacy", textContent: t("privacy"),
    onclick: () => dialogs.openPrivacy() });
  const accessibility = el("button", { type: "button", id: "accessibility", textContent: t("accessibility"),
    onclick: () => dialogs.openAccessibility() });

  if (site.mode === "site") {
    const installButton = el("button", { type: "button", id: "install", textContent: t("install"),
      title: t("installTitle"), hidden: install.isInstalled(),
      onclick: async () => { if (!install.canPrompt()) dialogs.openInstallHelp(); else await install.prompt(); } });
    install.onInstalled(() => { installButton.hidden = true; });
    const download = el("a", { id: "download", className: "button", href: site.downloadName,
      download: site.downloadName, textContent: `⬇ ${t("download")}`, title: t("downloadTitle") });
    slot.append(installButton, download, privacy, accessibility, status);
    return { setStatus };
  }

  slot.append(privacy, accessibility, status);
  setStatus(t("offlineCopy", { version: shortVersion(site.version), date: displayDate(site.date) }));
  if (site.siteUrl) {
    const runCheck = async (): Promise<void> => {
      const result = await checkForUpdate(site, net);
      if (result.kind === "up-to-date") setStatus(t("upToDate"));
      else if (result.kind === "available") {
        const wrap = el("span", {}, `${t("updateAvailable")} (${displayDate(result.info.date)}) — `,
          el("a", { href: result.downloadUrl, textContent: t("updateDownload") }));
        setStatus(wrap, true);
      } else if (result.kind === "failed") {
        console.warn(`Update check failed: ${result.reason}`);
        setStatus(t("updateUnknown"));
      }
    };
    slot.insertBefore(el("button", { type: "button", id: "check-update", textContent: t("checkUpdate"),
      onclick: () => { void runCheck(); } }), privacy);
    // Already "always allowed" → check silently on open; otherwise wait for a click.
    if (consent.state(new URL(site.siteUrl).origin) === "always") void runCheck();
  }
  return { setStatus };
}
