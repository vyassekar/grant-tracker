# Grant Tracker

Local single-user Flask + SQLite webapp for tracking research grants, spending, and
student allocations. See `README.md` for the user-facing feature list and setup steps.

## Running it

```
source venv/bin/activate
python app.py                    # http://127.0.0.1:5000
python seed_demo.py               # (re)populate demo data under data/*.db
```

There's no test suite. Verify changes by running the app and clicking through the
affected flow in a browser (dashboard → grant/student detail → departments →
scenarios), ideally against `seed_demo.py` data.

## Architecture

- **`app.py`** — the entire application: routes, SQLite access, and cost-calculation
  logic. No blueprints/models layer; everything lives in this one file by design, and
  it's small enough that this hasn't caused pain.
- **`schema.sql`** — canonical schema, executed once when a faculty `.db` file is first
  created (`init_db()`).
- **`templates/*.html`** — Jinja templates, one per page, extending `base.html`. Forms
  post directly to route handlers and redirect back (no JS framework, minimal
  hand-written JS inline in a couple of templates).
- **`static/style.css`** — one shared stylesheet, plain CSS with custom properties.
  Light/dark theming works by overriding those properties under
  `:root[data-theme="dark"]`; the `data-theme` attribute is set by inline JS in
  `base.html` (before first paint, from `localStorage` or `prefers-color-scheme`) and
  flipped by the header's toggle button. New chrome-level colors (page/card
  backgrounds) should go through a variable (`--bg`, `--surface`, etc.), not a literal
  like `white`, or they'll stay wrong in dark mode. Badge/banner colors are
  intentionally left as fixed pastels in both themes — that's a deliberate choice, not
  an oversight.
- **`data/*.db`** — one SQLite file per faculty member. Never shared across faculty;
  switching faculty in the UI just repoints the session at a different file. These
  files (except the two demo ones under version control via `seed_demo.py`) are
  real user data — don't delete or overwrite them without asking. **Never test writes
  (curl/sqlite3/script) against a real faculty `.db` directly** — use the demo
  databases (`seed_demo.py`) for that, or copy a real file aside first. `data/` is
  entirely gitignored, so nothing here is recoverable from git if it's overwritten.
  `backup_before_write()` in `app.py` snapshots a faculty db to
  `data/<slug>.db.bak-YYYYMMDD` before its first POST of the day — a same-day rollback
  net, not a substitute for care (see the safety-net comment in that function for why
  it exists).

## Data model

- `grants` — one row per award. Carries its own `overhead_rate_bps` (F&A rate; varies
  by sponsor, not department). `category` (`'sponsored'`, `'gift'`, or `'internal'`,
  validated by `parse_category()`/`GRANT_CATEGORIES`) drives the dashboard's toggle
  filter (`?category=` query param on `/`) — purely a classification, doesn't affect
  cost math. The dashboard also has an independent `?hide_closed=1` toggle that drops
  expired grants and any with a negative `balance_cents` (spent beyond the awarded
  total) from view; the two query params compose and each toggle's links preserve the
  other's current value (see `index()` and `index.html`).
- `departments` — per-department **default** billing rates: `stipend_cents_per_month`,
  `tuition_cents_per_month`, `fringe_rate_bps`. The stipend is a default only — see
  below.
- `students` — despite the table name, this holds both students and postdocs;
  `role` (`'student'` or `'postdoc'`, validated by `parse_role()`/`STUDENT_ROLES` in
  `app.py`) distinguishes them for display only — nothing else in the data model or
  cost logic treats them differently. `stipend_cents_per_month` is stored per person
  (not just looked up from `departments`), so it can diverge from the department
  default. The app auto-fills it from the person's department when the department is
  picked/changed in the add/edit form (inline `onchange` JS in `index.html` /
  `student_detail.html`, driven by a `deptStipends` JS object rendered from the
  `departments` list) — but the value is editable afterward and that's what cost
  calculations use. `start_date` / `expected_graduation` (nullable ISO dates) — when
  set, allocation months outside that window aren't charged (see below).
- `transactions` — recorded spend against a grant, independent of projected cost.
- `allocations` — student × grant × month × percent. `scenario_id IS NULL` means live
  data; a non-null `scenario_id` is a cloned what-if universe (see `scenarios`).
- `scenarios` — named clone of live allocations that can be edited freely and later
  applied back to live data (`apply_scenario`) or discarded.

Money is always stored as integer cents; rates (fringe, overhead) as integer basis
points (100 = 1%). Use the `parse_money` / `parse_rate` / `money` / `rate`
helpers/filters rather than hand-rolling conversions.

### Cost calculation

`allocation_cost_cents()` in `app.py` computes stipend/tuition/fringe/overhead for one
student × grant × month × percent. Overhead is computed on stipend+fringe only
(tuition excluded, matching typical federal MTDC rules) — this is a fixed formula, not
configurable per institution; edit it in place if your accounting differs.

`is_chargeable(month_str, start_date_str, expected_graduation_str)` gates whether that
formula runs at all for a given month: a person's allocation percent is still recorded
and shown outside `[start_date, expected_graduation]`, but the projected cost for those
months is zero. A month that only partially overlaps the window (they start or graduate
mid-month) is still charged in full — monthly granularity, no proration. Templates shade
those months/cells with the `.post-grad` CSS class so the cutoff is visible, not just
silently absent from the totals.

### Spending risk

`grant_spending_risk(grant, grid)` in `app.py` flags a non-expired grant as
`'overspending'`, `'underspending'`, or `None` (on track). It extrapolates
`current_monthly_burn_cents(grid)` — the projected personnel cost for this calendar
month (or the nearest future month with an allocation, or 0 if none) — across the
grant's remaining months to its end date, and compares that projection to the grant's
remaining (unspent) `balance_cents`. `GRANT_OVERSPEND_RATIO` (1.15) and
`GRANT_UNDERSPEND_RATIO` (0.6) are the tunable thresholds — adjust them if the flag is
too noisy/quiet for your grants. This only looks at *projected personnel cost*, not
other recorded transaction categories (equipment, travel, etc.), so a grant with heavy
non-personnel spending won't necessarily be flagged even if it's genuinely at risk.

### Schema migrations

`schema.sql` only runs for a brand-new faculty `.db` file. Existing files don't get
schema changes automatically, so any new column needs an idempotent `ALTER TABLE` added
to `migrate_db()` in `app.py`, which runs on every `get_db()` connection (cheap `PRAGMA
table_info` check, safe to call repeatedly). Follow this pattern for future schema
changes instead of assuming `schema.sql` alone is enough — the running app must keep
working against every faculty member's existing `.db` file, not just fresh ones.

### What-if scenarios

A scenario is a full clone of live allocations at creation time (`scenario_id` copied
to a new value), editable independently via the same `apply_allocation()` used for live
data. `apply_scenario()` overwrites live allocations with the scenario's; there's no
merge/diff — it's all-or-nothing.

The "New scenario" form (`scenarios.html`) picks a student and shows their current live
allocation as a set of sliders (one per grant, plus an "add a grant" control), so you can
free up percent from one grant while adding it to another in a single save — a stacked
bar and running total make it visually obvious when you're over 100%. This posts
`grant_id[]`/`percent[]` arrays to `add_scenario()`, which validates and writes them via
`apply_allocation_batch()` — a *different* function from `apply_allocation()` (used by
the single-grant "Allocate to a grant" forms on the grant/student pages, unchanged).
The batch version validates the combined new state up front rather than one grant at a
time, which is what makes rebalancing between two grants possible in one call: checking
sequentially would reject "raise grant B" while grant A still holds the percent about to
be freed up. Current allocations are embedded as JSON (`live_allocations_by_student`,
grouped server-side in `scenarios_page()`) and read client-side by month — switching the
"From month" re-derives which grants/percents count as "current" for that month.

## Conventions

- Keep everything in `app.py` — don't split into blueprints/models unless the file
  actually becomes unwieldy; it's intentionally flat for a project this size.
- Server-rendered forms + redirect-after-post throughout; no client-side framework.
  Keep new UI consistent with that (plain `<form>` posts, `flash()` for errors,
  `<details>` for collapsible add/edit sections).
- All amounts round-trip through cents; never store or compare floating-point dollars.
- `data/*.db` files and `*.xlsx` exports are gitignored — don't add tracked binary
  data files without checking `.gitignore` first.
