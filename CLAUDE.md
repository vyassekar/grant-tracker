# Grant Tracker

Local single-user Flask + SQLite webapp for tracking research grants, spending, and
student allocations. See `README.md` for the user-facing feature list and setup steps.

## Running it

```
source venv/bin/activate
python app.py                    # http://127.0.0.1:5000
python seed_demo.py               # (re)populate demo data under data/*.db
```

There's a small pytest suite under `tests/` — run it with `./venv/bin/pytest` (or
just `pytest` with the venv active; `pip install -r requirements-dev.txt` first if
`pytest`/`openpyxl`/`playwright` aren't already installed). It covers the
parsing/cost/spending-risk helpers, allocation validation (`apply_allocation`/
`apply_allocation_batch`), `migrate_db()`'s schema-upgrade path against a
deliberately old-shaped database, and the "plan a new hire" capacity-report
algorithm, plus route-level tests for the add-student initial allocation, faculty
Excel import, and scenario-apply → live-recompute flows. `tests/conftest.py`'s
`client` fixture drives real Flask routes against a throwaway per-test `data/`
directory (never the real one); its `db` fixture is a plain sqlite3 connection to
that same throwaway faculty db for setup/assertions, deliberately *not* one opened
via a Flask request/app context — mixing a held-open `test_request_context()` with
the test client's own context management corrupts Flask's context stack, and mixing
an uncommitted write with a separate `client.post()` connection deadlocks SQLite, so
`conftest.py`'s `open_faculty_db()` connects with `isolation_level=None` (autocommit)
instead. This is unit/integration-level, not browser-level, so still verify UI
changes by running the app and clicking through the affected flow in a browser
(dashboard → grant/student detail → departments → scenarios → settings), ideally
against `seed_demo.py` data.

`python record_demo.py` (same `requirements-dev.txt`, plus a one-time
`playwright install chromium`) reseeds demo data, drives a scripted walkthrough of
the app in headless Chromium, and (re)writes `demo/grant_tracker_demo.mp4` — update
its `run_walkthrough()` alongside any UI feature worth showing off, then re-run it
and commit the refreshed video.

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
  databases (`seed_demo.py`) for that, a temp dir (see the pytest fixtures in
  `tests/conftest.py`), or copy a real file aside first. `data/` is entirely
  gitignored, so nothing here is recoverable from git if it's overwritten.
  `backup_before_write()` in `app.py` snapshots a faculty db to
  `data/<slug>.db.bak-YYYYMMDD` before its first POST of the day — a same-day rollback
  net, not a substitute for care (see the safety-net comment in that function for why
  it exists).
- **`tests/`** — pytest suite (see "Running it" above). `conftest.py` holds the
  `client`/`faculty_slug`/`db` fixtures and small `insert_department()`/
  `insert_grant()`/`insert_student()`/`insert_allocation()`/`insert_transaction()`
  row-builders (mirroring `seed_demo.py`'s helpers, but scoped to a single throwaway
  faculty db per test).

## Data model

- `grants` — one row per award. Carries its own `overhead_rate_bps` (F&A rate; varies
  by sponsor, not department). `category` (`'sponsored'`, `'gift'`, or `'internal'`,
  validated by `parse_category()`/`GRANT_CATEGORIES`) drives the dashboard's category
  filter — purely a classification, doesn't affect cost math. It's multi-select: `/`
  takes zero or more repeated `?category=` params (`category_filter` in `index()` is a
  `set`), and each pill's link toggles just that one category in/out of the current
  selection via `category_toggle_urls` (precomputed server-side with `url_for(...,
  category=<new set>)` rather than in the template, since building that per-pill "set
  XOR one value, keep everything else" URL is easier in Python than Jinja). The
  dashboard also has an independent `?hide_closed=1` toggle (a single pill, not a
  pair — `hide_closed_toggle_url`) that drops expired grants and any with a negative
  `balance_cents` (spent beyond the awarded total) from view. Both filters compose and
  preserve each other's current state across clicks.
- `departments` — per-department **default** billing rates: `stipend_cents_per_month`,
  `tuition_cents_per_month`, `fringe_rate_bps`. The stipend is a default only — see
  below. `tuition_charged_in_summer` (boolean, default on) — when off, the tuition
  component (only; stipend/fringe/overhead are unaffected) is zeroed for that
  department's students in June/July/August allocation months. See "Cost calculation"
  below for exactly where that's applied.
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
  set, allocation months outside that window aren't charged (see below). The
  add-student form (`index.html`) can also set an initial multi-grant allocation split
  at creation time via the same slider editor scenarios use (see "What-if scenarios"
  below) — `add_student()` writes it with `apply_allocation_batch()` right after the
  `INSERT`, in the same uncommitted transaction, so an invalid split (over 100%)
  rolls back the whole student, not just the allocation.
- `transactions` — recorded spend against a grant, independent of projected cost.
- `allocations` — student × grant × month × percent. `scenario_id IS NULL` means live
  data; a non-null `scenario_id` is a cloned what-if universe (see `scenarios`).
- `scenarios` — named clone of live allocations that can be edited freely and later
  applied back to live data (`apply_scenario`) or discarded.
- `settings` — single row (`id = 1`) of grant-wide, institution-level knobs: currently
  just `overspend_ratio_bps`/`underspend_ratio_bps`, the spending-risk thresholds (see
  below), editable on the `/settings` page. Unlike every other table, new faculty dbs
  and existing ones both need this row to exist — `migrate_db()` creates the table
  and inserts its one default row if missing, using a `sqlite_master` existence check
  (a different idempotency pattern from the column-existence checks used for
  `ALTER TABLE` elsewhere in that function, since this is a whole new table, not a
  new column on an existing one).

Money is always stored as integer cents; rates (fringe, overhead, and now the
spending-risk ratios) as integer basis points (100 = 1%). Use the `parse_money` /
`parse_rate` / `money` / `rate` helpers/filters rather than hand-rolling conversions.

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

`is_summer_month(month_str)` (June/July/August) gates the department-level
`tuition_charged_in_summer` knob: when a department has it turned off, both
`grant_allocation_grid()` and `student_allocation_grid()` zero out that row's tuition
component immediately before calling `allocation_cost_cents()` for a summer month,
rather than the formula itself knowing about months — `allocation_cost_cents()` stays
a pure per-month function with no date awareness. The same zeroing is reused by the
new-hire capacity planner's `hire_window_cost_cents()` (see below), so a department's
summer-tuition setting is honored consistently in projections, live grids, and
what-if plans alike.

### Spending risk

`grant_spending_risk(grant, grid, overspend_ratio_bps, underspend_ratio_bps)` in
`app.py` flags a non-expired grant as `'overspending'`, `'underspending'`, or `None`
(on track). It extrapolates `current_monthly_burn_cents(grid)` — the projected
personnel cost for this calendar month (or the nearest future month with an
allocation, or 0 if none) — across the grant's remaining months to its end date, and
compares that projection to the grant's remaining (unspent) `balance_cents`. The two
ratio thresholds are **not** hardcoded constants — they're read per-request from the
`settings` table via `get_settings(db)` and passed in explicitly (defaults 115%/60%,
i.e. `overspend_ratio_bps=11500`/`underspend_ratio_bps=6000`, matching the values this
used to be fixed at), editable on the `/settings` page (`settings_page()`/
`update_settings()`) if the flag is too noisy/quiet for your grants — that route
rejects an underspend threshold at or above the overspend one, since an inverted/empty
"on track" band would be a confusing config rather than a useful one. This only looks
at *projected personnel cost*, not other recorded transaction categories (equipment,
travel, etc.), so a grant with heavy non-personnel spending won't necessarily be
flagged even if it's genuinely at risk.

Because `grant_with_balance()`/`grant_allocation_grid()`/`grant_spending_risk()` are
all computed fresh from the live `allocations`/`transactions` tables on every request
(`index()` and `grant_detail()`, nothing cached or stored), applying a scenario to
live data (`apply_scenario()`) is automatically reflected in the risk badge on the very
next page load — there's no separate recompute step to remember to call.

### Under-allocated warnings

`under_allocated_months(grid)` in `app.py` takes a `student_allocation_grid()` result
and returns the chargeable months where the total allocated percent is under 100 —
i.e. the student has unclaimed effort that could still be put on a grant. It's surfaced
two places: a hint on `student_detail.html` (via `student_detail()`'s `grid` for
whichever universe — live or a scenario — is currently being viewed), and a
"Under 100%" badge next to the existing "Changed" badge on `scenario_detail.html`'s
per-student table (via a `scenario_grid` already computed there for the cost columns).
Both reuse the one helper rather than duplicating the under-100 check.

### Schema migrations

`schema.sql` only runs for a brand-new faculty `.db` file. Existing files don't get
schema changes automatically, so any new column needs an idempotent `ALTER TABLE` added
to `migrate_db()` in `app.py`, which runs on every `get_db()` connection (cheap `PRAGMA
table_info` check, safe to call repeatedly) — a brand-new *table* (like `settings`)
instead needs a `sqlite_master` existence check, see that table's entry in "Data
model" above. Follow this pattern for future schema changes instead of assuming
`schema.sql` alone is enough — the running app must keep working against every faculty
member's existing `.db` file, not just fresh ones. `tests/test_migrations.py` builds a
deliberately old-shaped database by hand and asserts `migrate_db()` brings it current
(new columns/tables with the right defaults, existing data untouched, safe to run
more than once) — extend it alongside any future migration.

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
be freed up.

The slider editor itself lives in `templates/_allocation_editor.html`, included (not
extended — it's meant to sit inside a `<form>` the parent page already opened) by
`scenarios.html`, `scenario_detail.html`, and (for an optional initial split when
creating a brand-new student, no existing allocation to seed from) `index.html`'s
add-student form. It expects `students`, `grants_json` (`[{id, name}, ...]`), `today`,
and `baseline_allocations_by_student` (grouped by `allocations_grouped_by_student()`)
in the including template's context, plus an optional `show_student_picker` (defaults
`true`) — set to `false` to omit the student `<select>` entirely and start the editor
from an empty baseline immediately (via a `DOMContentLoaded` render instead of the
picker's `onchange`), which is what `index.html` does since the student doesn't exist
yet to have a "current" allocation. Where a picker is shown, the difference between
the two call sites' `baseline_allocations_by_student` is *which* allocations count as
"current": live data on the creation form, that scenario's own data on
`scenario_detail.html`'s "Add a change" form, so edits build on whatever a
multi-student scenario already contains rather than always resetting to live.

`scenario_detail.html` (`GET /scenarios/<id>`) is where a scenario spanning several
students comes together: it lists every student and grant touched in either live or the
scenario (via set union, so removals show up too), a "Changed" badge from
`scenario_changed_student_ids()` (a symmetric-difference of the two universes' allocation
rows) marks who's actually been edited, and the overall "Projected personnel" stat sums
every grant's scenario-vs-live cost — the combined effect of however many students'
changes have been layered in. `add_scenario()` redirects here after creating a scenario
(instead of straight to the student page) so building out a multi-student scenario is a
loop over this one page: pick a student in "Add a change," adjust, save, repeat.

### Plan a new hire (capacity report)

`GET /scenarios/plan-new-student` (`plan_new_student()`) is a **read-only** report —
unlike everything else under Scenarios, it never writes a student, allocation, or
scenario. Given a time window and a set of hypothetical hires (department + role +
count, assumed 100% effort for the whole window), it answers "do current grants have
enough uncommitted balance to cover this, and how might it be split?" `GET`, not
`POST`, since there's no side effect to protect against a page reload/back-button.

- `eligible_grants_for_window(db, months)` narrows to non-expired grants whose
  `[start_date, end_date]` fully covers the window, excluding (with a reason, shown in
  a transparency panel) anything expired, partially-covering, or with no
  `grant_spare_capacity_cents()` left.
- `grant_spare_capacity_cents(grant, months)` is remaining balance minus that grant's
  already-committed live cost **within the window only** — it does not reserve balance
  for commitments outside the window, so a grant heavily committed just past the
  window's edge can still show its full uncommitted balance as spare (documented as a
  caveat in `plan_new_student.html`, not hidden).
- `hire_window_cost_cents(department, overhead_rate_bps, months)` is the window cost of
  one hypothetical 100%-effort hire, reusing `allocation_cost_cents()` and the summer-
  tuition rule — no new cost math.
- Three heuristic plans, not an LP solver (deliberately — this is meant to be legible,
  not optimal): `build_greedy_hire_plan()` (parameterized by grant ordering) drives
  both "Concentrate" (most-spare-capacity-first) and "Use it or lose it"
  (soonest-expiring-first) by draining one shared `spare_remaining` pool per grant
  across hires processed in submitted order, so a grant is naturally exhausted before
  later hires spill onto the next one in the order. `build_spread_hire_plan()` instead
  splits each hire proportionally across every grant with remaining capacity, using
  largest-remainder rounding so per-grant percentages always sum exactly to the
  feasible total.
- Money bookkeeping inside these plan-builders is float, not integer cents — this is a
  report, not a ledger write, so accumulated float error across many hires/grants is
  fine; everything actually persisted to the database elsewhere in the app stays
  integer cents as always.

## Importing grants

`import_from_excel.py` is a standalone CLI for bulk-importing active grants (plus a
lump-sum "spent so far" transaction per grant) from a grant-report `.xlsx` into a
faculty db — see its module docstring for the expected report format and header
detection. Its parsing functions (`find_header`, `build_grant_records`,
`existing_ptas`, etc.) are plain functions decoupled from the CLI/argparse and from
its own `open_db()`/`sqlite3.connect`, so `add_faculty()` in `app.py` reuses them
directly: the "New faculty member" form (`faculty.html`) has an optional file upload,
and `import_grants_from_workbook()` runs the same header-detection/parsing pipeline
against the upload (via `openpyxl.load_workbook(BytesIO(...))`) with the CLI's default
options (today as as-of-date, 3-year estimated start date, excludes expired awards),
writing into the faculty db that was just created. A workbook that fails to parse or
doesn't match the expected report format doesn't undo the faculty creation — the
(now-empty) faculty db stays around either way, with a `flash()` explaining what
happened, consistent with the rest of the app's "never silently destroy data" posture.

## Conventions

- Keep everything in `app.py` — don't split into blueprints/models unless the file
  actually becomes unwieldy; it's intentionally flat for a project this size.
- Server-rendered forms + redirect-after-post throughout; no client-side framework.
  Keep new UI consistent with that (plain `<form>` posts, `flash()` for errors,
  `<details>` for collapsible add/edit sections). `GET` is reserved for routes with no
  side effects (see "Plan a new hire" above) — everything that writes stays `POST` +
  redirect.
- All amounts round-trip through cents; never store or compare floating-point dollars
  in anything persisted to the database. (The new-hire planner's in-memory
  spare-capacity bookkeeping is an intentional, documented exception — see above.)
- `data/*.db` files and `*.xlsx` exports are gitignored — don't add tracked binary
  data files without checking `.gitignore` first.
- New calculation/validation logic should get a pytest test alongside it (see
  "Running it" and `tests/`), not just manual browser verification — especially
  anything with edge cases (rounding, thresholds, migrations) that's easy to get
  subtly wrong and hard to eyeball in a browser.
