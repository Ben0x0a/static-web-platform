"""credentials.py — refuse to publish credentials: everything in public/ is public.

Defines : find_secrets(), check_secrets(), SECRET_PATTERNS.
Used by : builder.py (before anything is written to public/).
Uses    : nothing.

WHY: a local-first app has no server to hide a key behind. Whatever the page,
the single file, the zip or the CLI holds ships to every visitor — including
anything a bundler inlines from the environment (e.g. Vite's VITE_* variables).
So an app may only call keyless public services; a key found in the output is
a build error, never a warning. A key that was ever published is leaked:
rotate it, removing it is not enough.

The patterns are formats whose prefix is specific enough to give no false
positives in ordinary code: they catch the common accidents, not every secret.
"""

import re

SECRET_PATTERNS: dict[str, re.Pattern[bytes]] = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY"),
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,})"),
    "Google API key": re.compile(rb"\bAIza[0-9A-Za-z_\-]{35}"),
    "Stripe secret key": re.compile(rb"\b(?:sk|rk)_live_[0-9A-Za-z]{20,}"),
    "Slack token": re.compile(rb"\bxox[abposr]-[0-9A-Za-z-]{10,}"),
    "OpenAI / Anthropic key": re.compile(rb"\bsk-(?:proj-|ant-)[A-Za-z0-9_\-]{20,}"),
}


def find_secrets(files: dict[str, bytes]) -> list[str]:
    """One line per hit: file, kind and a masked excerpt (the secret itself is never printed)."""
    hits = []
    for name in sorted(files):
        for kind, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(files[name]):
                hits.append(f"{name}: {kind} ({match.group()[:6].decode('ascii', 'replace')}…)")
    return hits


def check_secrets(files: dict[str, bytes]) -> None:
    hits = find_secrets(files)
    if hits:
        raise SystemExit("Refusing to publish what looks like credentials (everything published is public;\n"
                         "use keyless services only, and rotate any key that was ever committed):\n  "
                         + "\n  ".join(hits))
