CREATE TABLE grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sponsor TEXT,
    total_amount_cents INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    -- Negotiated F&A/indirect cost rate for this grant, in basis points (100 = 1%).
    overhead_rate_bps INTEGER NOT NULL DEFAULT 0,
    -- 'sponsored' (external award, typically carries F&A), 'gift', or 'internal'
    -- (departmental/discretionary funds). See GRANT_CATEGORIES in app.py.
    category TEXT NOT NULL DEFAULT 'sponsored',
    notes TEXT
);

-- Departmental billing rates: default stipend, tuition remission, and fringe
-- benefit rate for students in that department. These vary by department;
-- overhead varies by grant instead (see grants.overhead_rate_bps), since F&A
-- rates are negotiated per sponsor, not per department.
CREATE TABLE departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    stipend_cents_per_month INTEGER NOT NULL DEFAULT 0,
    tuition_cents_per_month INTEGER NOT NULL DEFAULT 0,
    fringe_rate_bps INTEGER NOT NULL DEFAULT 0,
    -- Whether tuition remission is billed for allocation months in June/July/August.
    -- Some programs don't charge tuition over the summer; see is_summer_month() in app.py.
    tuition_charged_in_summer INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    department_id INTEGER REFERENCES departments(id),
    -- 'student' or 'postdoc'. Both are tracked in this same table (grants/allocations
    -- don't otherwise care which); the app enforces the two allowed values.
    role TEXT NOT NULL DEFAULT 'student',
    -- Defaults to the department's stipend when set via the app; stored per-student
    -- so it can still be overridden for students who differ from their department's rate.
    stipend_cents_per_month INTEGER NOT NULL DEFAULT 0,
    -- ISO dates (YYYY-MM-DD), both optional. When set, no personnel cost is projected
    -- for allocation months entirely outside [start_date, expected_graduation] --
    -- see is_chargeable() in app.py.
    start_date TEXT,
    expected_graduation TEXT,
    notes TEXT
);

CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grant_id INTEGER NOT NULL REFERENCES grants(id),
    date TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    description TEXT
);

-- A scenario is a named "what-if" universe. scenario_id = NULL means live data.
CREATE TABLE scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- One row = this student is allocated this % of their time to this grant in this month.
CREATE TABLE allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id INTEGER REFERENCES scenarios(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    grant_id INTEGER NOT NULL REFERENCES grants(id),
    month TEXT NOT NULL,
    percent INTEGER NOT NULL
);

CREATE INDEX idx_transactions_grant ON transactions(grant_id);
CREATE INDEX idx_allocations_student ON allocations(student_id, scenario_id);
CREATE INDEX idx_allocations_grant ON allocations(grant_id, scenario_id);
CREATE INDEX idx_students_department ON students(department_id);

-- Single-row table of tunable knobs. See GRANT_OVERSPEND_RATIO/GRANT_UNDERSPEND_RATIO
-- in app.py: a grant's projected burn vs. remaining balance is flagged 'overspending'
-- above overspend_ratio_bps, 'underspending' below underspend_ratio_bps (100 = 1%,
-- so the default 11500/6000 is 115%/60%, matching the previous hardcoded constants).
CREATE TABLE settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    overspend_ratio_bps INTEGER NOT NULL DEFAULT 11500,
    underspend_ratio_bps INTEGER NOT NULL DEFAULT 6000
);
INSERT INTO settings (id, overspend_ratio_bps, underspend_ratio_bps) VALUES (1, 11500, 6000);
