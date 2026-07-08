# Grant Tracker

Local single-user webapp for tracking research grants, spending, and student
allocations.

**Demo video:** [demo/grant_tracker_demo.mp4](demo/grant_tracker_demo.mp4) — a ~40s
walkthrough recorded against the seeded sample data (dark/light theme toggle, grant
category filtering, hiding expired/overspent grants, an overspending risk flag on a
grant detail page, department stipend auto-fill, and building a what-if scenario across
two students with the slider allocation editor to see their combined projected-cost
effect).

- Track grant balances (recorded transactions) and expiration status.
- Allocate students to grants by month and percent of effort — a student can
  split time across multiple grants in the same month.
- View allocation by grant (which students, what %, over time) or by student
  (which grants, what %, over time), each as a month-by-month grid.
- Each student has a monthly stipend and an optional department. Departments
  carry a default stipend, a tuition remission rate ($/month), and a fringe
  benefit rate (% of stipend); each grant carries its own overhead/F&A rate.
  Picking a department on a student auto-fills its default stipend, but the
  amount is still editable per student. Grant and student pages show a
  projected personnel cost breakdown (stipend / tuition / fringe / overhead)
  per month, alongside the recorded transaction balance. Overhead is computed
  on stipend+fringe only (tuition is excluded from the overhead base, matching
  typical federal MTDC rules) — adjust the formula in `allocation_cost_cents()`
  in `app.py` if your institution's accounting differs.
- A student can have an expected graduation date. No personnel cost is
  projected for allocation months after that date (their allocation % still
  shows, shaded, so the record isn't silently dropped — just not charged).
- "What-if" scenarios: clone live allocations into a named scenario, move
  students around freely without touching real data, compare projected cost
  against live, and apply the scenario to live data when you're happy with it.
- Multiple faculty members: each gets their own separate database file under
  `data/` (e.g. `data/jane_smith.db`). The first screen you see lets you pick
  an existing faculty member or create a new one; switching is instant, no
  restart needed. There's no "delete faculty" button in the UI on purpose —
  that would be a one-click full-data wipe. To remove one, delete its file
  under `data/` directly.

## Requirements

- Python 3.9 or newer (tested on 3.13). Check with `python3 --version`.
- macOS, Linux, or Windows — no OS-specific dependencies.
- Everything else (Flask) is installed into a local virtual environment by
  the steps below; there's no database server or system package to install.
  SQLite ships with Python's standard library.

## Run

```
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** in a browser. You'll land on a faculty
picker first — pick an existing faculty member or create a new one. Each
faculty member's data lives in its own file under `data/`; back one up by
copying that file. Leave the terminal window running while you use the app;
press `Ctrl+C` in it to stop the server.

### Optional: load sample data

To explore the app immediately with realistic example data instead of
starting empty:

```
python seed_demo.py
```

This creates two demo faculty databases under `data/`:

- **Dr. Maria Santos** — 6 grants spanning all three categories (sponsored,
  gift, internal) and every status (expired, expiring soon, active, one
  flagged overspending), 5 students/postdocs split across 3 departments
  with overlapping and partial allocations, recorded transactions, and one
  pre-built what-if scenario spanning multiple students.
- **Dr. Alex Rivera** — a smaller second dataset, mainly to show that
  switching faculty members keeps data fully separate.

Re-running `seed_demo.py` replaces both from scratch — it's safe to run
again, but don't run it if you've already entered real data for a faculty
member named "Dr. Maria Santos" or "Dr. Alex Rivera" (it will overwrite that
database).

### Optional: regenerate the demo video

The video above was produced with Playwright driving a real headless
browser against the seeded data. To regenerate it after changing the app or
the seed data:

```
pip install -r requirements-dev.txt
playwright install chromium
python record_demo.py
```

This reseeds the demo data, launches the app on a scratch port, records the
walkthrough, and writes `demo/grant_tracker_demo.mp4` (falls back to a
`.webm` if no `ffmpeg` is found on your system — install `ffmpeg` for a
proper mp4).

## Install as a standalone desktop app (macOS / Windows)

Instead of running a dev server and opening a browser tab, you can run Grant
Tracker as a real desktop app — `GrantTracker.app` on macOS, `GrantTracker.exe` on
Windows — that opens in its own window, with no terminal window to keep open. This
still runs entirely on your machine — no data ever leaves it, there's no server to
reach it from the network, and no account or internet connection is needed. It's a
separate, self-contained data store from the dev-server flow above (see where its
data lives, below) — the two don't share faculty databases automatically.

**Already-built, ready to run:** [`dist/`](dist/README.md) has a prebuilt copy of
both — skip straight there if you just want to run the app, no Python needed. The
steps below are for building it yourself instead (e.g. after changing the code).

### macOS

1. Follow the **Requirements** + first three lines of **Run** above to get a venv
   with `requirements.txt` installed, then also install the desktop-only
   dependencies:
   ```
   pip install -r requirements-desktop.txt
   ```
2. Build the app bundle:
   ```
   pyinstaller GrantTracker.spec --noconfirm
   ```
   This produces `dist/GrantTracker.app` (~30MB, takes under a minute).
3. Drag `dist/GrantTracker.app` into `/Applications` (or just double-click it in
   place — either works).
4. **First launch only:** since this is an unsigned build (no Apple Developer ID),
   double-clicking will show a "can't be opened because Apple cannot check it for
   malicious software" warning. Instead, **right-click (or Control-click)
   `GrantTracker.app` → Open**, then click **Open** again in the dialog that
   appears. You only need to do this once — after that, it opens normally like any
   other app, including from Spotlight/Launchpad.

Its data lives at `~/Library/Application Support/Grant Tracker/data/` (one file per
faculty member, separate from the `data/` folder used by `python app.py` above) —
back it up by copying that folder. Quitting the app (Cmd+Q or closing its window)
stops everything; nothing is left running in the background.

To rebuild after changing the app's code, just re-run step 2 — `dist/` and `build/`
are safe to delete and regenerate anytime, they're not where your data lives.

### Windows

Same `GrantTracker.spec`, built the same way, but needs to run on an actual Windows
machine (PyInstaller doesn't cross-compile) — either your own, or via
`.github/workflows/build-desktop.yml` on a GitHub Actions `windows-latest` runner
(Actions tab → "Build desktop app" → "Run workflow", then download the
`GrantTracker-Windows` artifact).

1. On Windows, with a venv set up the same way as **Requirements** + **Run**
   describe (`venv\Scripts\activate` instead of `source venv/bin/activate`):
   ```
   pip install -r requirements.txt
   pip install -r requirements-desktop.txt
   pyinstaller GrantTracker.spec --noconfirm
   ```
   This produces `dist/GrantTracker/GrantTracker.exe` plus its `_internal/` folder
   — copy the whole `dist/GrantTracker/` folder wherever you want to run it from;
   the `.exe` needs `_internal/` next to it.
2. Double-click `GrantTracker.exe`.
3. **First launch only:** this build is unsigned (no code-signing certificate), so
   Windows SmartScreen will likely show an "unrecognized app" warning. Click
   **More info**, then **Run anyway**. You only need to do this once.
4. Needs the Microsoft Edge WebView2 runtime, which ships by default on Windows
   11 and most updated Windows 10 installs; Windows will prompt to install it
   automatically if it's genuinely missing.

Its data lives at `%APPDATA%\Grant Tracker\data\`. This build path has been
verified to compile cleanly and bundle every required file (checked via CI), but
hasn't yet been confirmed launching on real Windows hardware — see
[`dist/README.md`](dist/README.md) for the current status of the committed build.

### Optional: record a desktop-app demo video

The demo video at the top of this file is browser-driven (Playwright/Chromium
against the regular dev server) — that approach doesn't work for the native
`GrantTracker.app` window (pywebview's window is a real OS window, not something a
browser-automation tool can attach to or capture). Instead:

```
python record_desktop_demo.py
```

This reseeds demo data, finds your Mac's screen-capture device, launches
`GrantTracker.app`, and walks you through a ~90s recording (it prints a suggested
click-through checklist) — actually clicking through the app is on you, since this
part can't be automated. Needs `ffmpeg` and one-time Screen Recording permission
for your terminal app (macOS will prompt). Writes
`demo/grant_tracker_desktop_demo.mp4` — a separate file; it never touches the
existing `demo/grant_tracker_demo.mp4`.
