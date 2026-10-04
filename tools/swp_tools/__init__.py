"""swp_tools — build, verification and helper tools of static-web-platform.

Package layout (one responsibility per module):
  config.py    Project: paths + validated site.json (data container)
  version.py   source fingerprint (version) of an app + its platform
  csp.py       Content-Security-Policy of each output
  bundle.py    type check (tsc) + app bundle (esbuild, or the app's own command)
  assemble.py  page assembly (site + single file), config.js, manifest, headers, sw.js
  builder.py   build / check / verify orchestration
  serve.py     local server applying _headers (tests)
  gate.py      verification gate (Playwright + Chrome + axe-core)
  icons.py     icon.svg → PNG sizes
  cli.py       the `swp` command (thin: parses arguments, dispatches)
"""
