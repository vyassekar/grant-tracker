CREATE TABLE grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sponsor TEXT,
    total_amount_cents INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    -- Negotiated F&A/indirect cost rate for this grant, in basis points (100 = 1%).
    overhead_rate_bps INTEGER NOT NULL DEFAULT 0,
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
    fringe_rate_bps INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    department_id INTEGER REFERENCES departments(id),
    -- Defaults to the department's stipend when set via the app; stored per-student
    -- so it can still be overridden for students who differ from their department's rate.
    stipend_cents_per_month INTEGER NOT NULL DEFAULT 0,
    -- ISO date (YYYY-MM-DD). When set, no personnel cost is projected for allocation
    -- months starting after this date -- see is_chargeable() in app.py.
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
