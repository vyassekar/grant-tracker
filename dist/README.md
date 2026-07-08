# GrantTracker.app — prebuilt macOS app

A ready-to-run build of Grant Tracker, committed here so people can try it without
installing Python or building from source. See the main [README](../README.md) for
what the app does and how to build this yourself; this file just covers installing
*this specific committed build*.

## Install

1. Download/clone this repo, then drag `dist/GrantTracker.app` into `/Applications`
   (or run it right from here — either works).
2. **First launch only:** this build is unsigned (no Apple Developer ID), so
   double-clicking will show a "can't be opened because Apple cannot check it for
   malicious software" warning. Instead, **right-click (or Control-click)
   `GrantTracker.app` → Open**, then click **Open** again in the dialog that
   appears. You only need to do this once — after that it opens normally,
   including from Spotlight/Launchpad.
3. That's it — no Python, no terminal, no internet connection needed.

## What this is

- **Platform:** macOS, **Apple Silicon (arm64) only** — this was built on an M-series
  Mac and is not a universal2 binary, so it won't launch on an Intel Mac. If you need
  an Intel build, build it yourself from source on an Intel Mac (see the main
  README's "Install as a standalone desktop app" section) or ask for a universal2
  build.
- **Built from commit:** `6fa944a` (2026-07-08).
- **Executable checksum (sha256):**
  `c6dc19f83565cd144f37b4a076ad535814cabc54d711f20c9b6832f335e40a88`
  (`shasum -a 256 GrantTracker.app/Contents/MacOS/GrantTracker` to verify).
- **Data:** stored locally at `~/Library/Application Support/Grant Tracker/data/`
  (one SQLite file per faculty member), created on first launch. Nothing is ever
  sent over the network — the app only listens on `127.0.0.1`, and there are no
  external API calls anywhere in the codebase.

## Updating

This committed build doesn't auto-update. When the app changes, a new
`GrantTracker.app` needs to be rebuilt and committed here (`pyinstaller
GrantTracker.spec --noconfirm` from the repo root, see the main README) to replace
this one — check the "Built from commit" line above against `git log` to see if
you're behind.
