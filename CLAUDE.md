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
- **`data/*.db`** — one SQLite file per faculty member. Never shared across faculty;
  switching faculty in the UI just repoints the session at a different file. These
  files (except the two demo ones under version control via `seed_demo.py`) are
  real user data — don't delete or overwrite them without asking.

## Data model

- `grants` — one row per award. Carries its own `overhead_rate_bps` (F&A rate; varies
  by sponsor, not department).
- `departments` — per-department **default** billing rates: `stipend_cents_per_month`,
  `tuition_cents_per_month`, `fringe_rate_bps`. The stipend is a default only — see
  below.
- `students` — `stipend_cents_per_month` is stored per student (not just looked up
  from `departments`), so it can diverge from the department default. The app
  auto-fills it from the student's department when the department is picked/changed
  in the add/edit form (inline `onchange` JS in `index.html` / `student_detail.html`,
  driven by a `deptStipends` JS object rendered from the `departments` list) — but the
  value is editable afterward and that's what cost calculations use.
  `expected_graduation` (nullable ISO date) — when set, allocation months starting
  after this date aren't charged (see below).
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

`is_chargeable(month_str, expected_graduation_str)` gates whether that formula runs at
all for a given month: a student's allocation percent is still recorded and shown past
their `expected_graduation`, but the projected cost for those months is zero. The month
graduation falls in is still charged in full (monthly granularity, no proration).
Templates shade those months/cells with the `.post-grad` CSS class so the cutoff is
visible, not just silently absent from the totals.

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

## Conventions

- Keep everything in `app.py` — don't split into blueprints/models unless the file
  actually becomes unwieldy; it's intentionally flat for a project this size.
- Server-rendered forms + redirect-after-post throughout; no client-side framework.
  Keep new UI consistent with that (plain `<form>` posts, `flash()` for errors,
  `<details>` for collapsible add/edit sections).
- All amounts round-trip through cents; never store or compare floating-point dollars.
- `data/*.db` files and `*.xlsx` exports are gitignored — don't add tracked binary
  data files without checking `.gitignore` first.
