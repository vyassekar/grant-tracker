# Prebuilt desktop app (macOS + Windows)

Ready-to-run builds of Grant Tracker, committed here so people can try it without
installing Python or building from source. See the main [README](../README.md) for
what the app does and how to build these yourself; this file just covers installing
*these specific committed builds*. Both are local-only: no data ever leaves your
machine, no account or internet connection is needed, and there are no external API
calls anywhere in the codebase.

## macOS — `GrantTracker.app`

1. Drag `dist/GrantTracker.app` into `/Applications` (or run it right from here —
   either works).
2. **First launch only:** this build is unsigned (no Apple Developer ID), so
   double-clicking will show a "can't be opened because Apple cannot check it for
   malicious software" warning. Instead, **right-click (or Control-click)
   `GrantTracker.app` → Open**, then click **Open** again in the dialog that
   appears. You only need to do this once — after that it opens normally,
   including from Spotlight/Launchpad.
3. Data lives at `~/Library/Application Support/Grant Tracker/data/`.

- **Platform:** macOS, **Apple Silicon (arm64) only** — built on an M-series Mac,
  not a universal2 binary, so it won't launch on an Intel Mac. If you need an Intel
  build, build it yourself on an Intel Mac (see the main README) or ask for a
  universal2 build.
- **Built from commit:** `6fa944a` (2026-07-08).
- **Executable checksum (sha256):**
  `c6dc19f83565cd144f37b4a076ad535814cabc54d711f20c9b6832f335e40a88`
  (`shasum -a 256 GrantTracker.app/Contents/MacOS/GrantTracker` to verify).

## Windows — `GrantTracker-Windows/`

1. Copy the whole `dist/GrantTracker-Windows/` folder anywhere you like (e.g.
   `Desktop` or `Documents`) — `GrantTracker.exe` needs the `_internal/` folder
   next to it, so don't move the `.exe` out on its own.
2. Double-click `GrantTracker.exe`.
3. **First launch only:** this build is unsigned (no code-signing certificate), so
   Windows SmartScreen will likely show a "Windows protected your PC" /
   "unrecognized app" warning. Click **More info**, then **Run anyway**. You only
   need to do this once.
4. Data lives at `%APPDATA%\Grant Tracker\data\`.

- **Platform:** Windows 10/11, x86-64. Needs the Microsoft Edge WebView2 runtime,
  which ships by default on Windows 11 and most updated Windows 10 installs (via
  Edge auto-update); Windows will prompt to install it automatically if it's
  genuinely missing.
- **Built from commit:** `66a72c8` (2026-07-08), via GitHub Actions'
  `windows-latest` runner (see `.github/workflows/build-desktop.yml`) — this build
  has been verified to compile cleanly and bundle all required files
  (`templates/`, `static/`, `schema.sql`, the WebView2/pythonnet dependencies), but
  **has not yet been confirmed to actually launch on real Windows hardware.** If
  you hit a problem running it, please report it.
- **Executable checksum (sha256):**
  `c42f50c8a3cf40f6eee10e7b3cf0f2969692e36700cd7f5e257e7ef5cbbb41d0`
  (`certutil -hashfile GrantTracker.exe SHA256` on Windows, or
  `shasum -a 256 GrantTracker.exe` on macOS/Linux, to verify).

## Updating

Neither build auto-updates. When the app changes, new builds need to be produced
and committed here to replace these — check each "Built from commit" line above
against `git log` to see if you're behind.

- macOS: `pyinstaller GrantTracker.spec --noconfirm` from the repo root (see the
  main README's "Install as a standalone desktop app" section), then commit the
  refreshed `dist/GrantTracker.app`.
- Windows: trigger `.github/workflows/build-desktop.yml` (Actions tab → "Build
  desktop app" → "Run workflow"), then download the `GrantTracker-Windows`
  artifact and commit its contents over `dist/GrantTracker-Windows/`.
