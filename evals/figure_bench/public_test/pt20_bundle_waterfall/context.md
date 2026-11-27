# Thread

**User:** Our web app's production JS bundle jumped noticeably in the
latest release candidate. The `esbuild`-format metafiles are in
`data/before_meta.json` and `data/after_meta.json`.

**Assistant:** Both metafiles describe `dist/app.bundle.js` with total
output `bytes` and per-module `bytesInOutput` contributions across `src/`
and `node_modules/`.

**User:** Show a breakdown of how we got from the previous bundle size to
the new one so we know what actually caused the bloat before shipping.

**Assistant:** I'll compute the module-level size deltas and show the
before-to-after bridge highlighting the main driver.

**User:** One figure I can attach to the release checklist, please.
