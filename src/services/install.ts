/*
  services/install.ts — PWA install support (no UI).

  Defines : createInstall() → { isInstalled, canPrompt, prompt, onInstalled }.
  Used by : ui/actions.ts (Install button).
  Uses    : browser events beforeinstallprompt / appinstalled.

  Chromium offers a native prompt (beforeinstallprompt, captured here as early
  as possible); Safari and iOS do not — the UI then shows instructions.
*/

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  readonly userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export interface Install {
  isInstalled(): boolean;
  canPrompt(): boolean;
  /** Show the native prompt; resolves true when the user accepted. */
  prompt(): Promise<boolean>;
  onInstalled(callback: () => void): void;
}

export function createInstall(): Install {
  let deferred: BeforeInstallPromptEvent | null = null;
  window.addEventListener("beforeinstallprompt", event => {
    event.preventDefault();
    deferred = event as BeforeInstallPromptEvent;
  });
  return {
    isInstalled: () =>
      matchMedia("(display-mode: standalone)").matches
      || (navigator as Navigator & { standalone?: boolean }).standalone === true,
    canPrompt: () => deferred !== null,
    async prompt() {
      if (!deferred) return false;
      await deferred.prompt();
      const { outcome } = await deferred.userChoice;
      deferred = null;
      return outcome === "accepted";
    },
    onInstalled(callback) { window.addEventListener("appinstalled", callback); },
  };
}
