"""Populate demo faculty databases with synthetic grants, students, and spending.

Run: ./venv/bin/python seed_demo.py

Creates two faculty databases under data/ so you can explore the app (and the
faculty-switching feature) immediately, without entering data by hand:
  - Dr. Maria Santos: a fuller dataset (4 grants, 5 students, a what-if scenario)
  - Dr. Alex Rivera: a smaller second dataset, to show data stays separate per faculty

Re-running this script replaces both databases from scratch.
"""
import sqlite3

from app import DATA_DIR, SCHEMA_PATH, slugify


def fresh_db(slug):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{slug}.db"
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA_PATH.read_text())
    return db, path


def insert_department(db, name, stipend_dollars, tuition_dollars, fringe_rate_percent):
    cur = db.execute(
        "INSERT INTO departments (name, stipend_cents_per_month, tuition_cents_per_month, fringe_rate_bps) VALUES (?, ?, ?, ?)",
        (name, round(stipend_dollars * 100), round(tuition_dollars * 100), round(fringe_rate_percent * 100)),
    )
    return cur.lastrowid


def insert_grant(db, name, sponsor, total_dollars, overhead_rate_percent, start_date, end_date, notes=""):
    cur = db.execute(
        """INSERT INTO grants (name, sponsor, total_amount_cents, start_date, end_date, overhead_rate_bps, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, sponsor, round(total_dollars * 100), start_date, end_date, round(overhead_rate_percent * 100), notes),
    )
    return cur.lastrowid


def insert_student(db, name, email, department_id, stipend_dollars, role="student", start_date=None,
                    expected_graduation=None, notes=""):
    cur = db.execute(
        """INSERT INTO students (name, email, department_id, role, stipend_cents_per_month, start_date,
           expected_graduation, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, email, department_id, role, round(stipend_dollars * 100), start_date, expected_graduation, notes),
    )
    return cur.lastrowid


def insert_transaction(db, grant_id, tx_date, amount_dollars, description):
    db.execute(
        "INSERT INTO transactions (grant_id, date, amount_cents, description) VALUES (?, ?, ?, ?)",
        (grant_id, tx_date, round(amount_dollars * 100), description),
    )


def month_range(start, end):
    """'2026-01' .. '2026-03' -> ['2026-01', '2026-02', '2026-03']"""
    start_year, start_month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    months = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def insert_allocation(db, scenario_id, student_id, grant_id, start_month, end_month, percent):
    for month in month_range(start_month, end_month):
        db.execute(
            "INSERT INTO allocations (scenario_id, student_id, grant_id, month, percent) VALUES (?, ?, ?, ?, ?)",
            (scenario_id, student_id, grant_id, month, percent),
        )


def seed_maria_santos():
    db, path = fresh_db(slugify("Dr. Maria Santos"))

    cs = insert_department(db, "Computer Science", stipend_dollars=3700, tuition_dollars=1200, fringe_rate_percent=28)
    bio = insert_department(db, "Biology", stipend_dollars=3400, tuition_dollars=1100, fringe_rate_percent=32)
    me = insert_department(db, "Mechanical Engineering", stipend_dollars=3900, tuition_dollars=1300, fringe_rate_percent=30)

    nsf = insert_grant(db, "NSF CAREER Award", "NSF", 500_000, 52, "2024-09-01", "2027-08-31")
    nih = insert_grant(db, "NIH R01 - Cancer Genomics", "NIH", 750_000, 61, "2023-04-01", "2026-08-15")
    doe = insert_grant(db, "DOE Early Career Award", "DOE", 400_000, 15, "2025-01-01", "2026-03-31")
    sloan = insert_grant(db, "Sloan Research Fellowship", "Alfred P. Sloan Foundation", 75_000, 0, "2025-09-01", "2027-08-31")

    chen = insert_student(db, "Maria Chen", "mchen@university.edu", cs, 3800, start_date="2023-09-01")
    # Starts mid-scenario, to demo that no personnel cost is projected before this date even
    # though his NIH/DOE allocations begin in 2026-01.
    okafor = insert_student(db, "David Okafor", "dokafor@university.edu", cs, 3600, role="postdoc",
                             start_date="2026-02-01")
    nair = insert_student(db, "Priya Nair", "pnair@university.edu", bio, 3400, start_date="2024-01-15")
    wilson = insert_student(db, "Sam Wilson", "swilson@university.edu", me, 3900, start_date="2022-09-01")
    # Graduating mid-scenario, to demo that no personnel cost is projected past this date
    # even though her NIH/scenario allocations continue through 2026-07.
    tanaka = insert_student(db, "Yuki Tanaka", "ytanaka@university.edu", bio, 3300,
                             start_date="2021-09-01", expected_graduation="2026-05-31")

    insert_allocation(db, None, chen, nsf, "2026-01", "2026-12", 100)
    insert_allocation(db, None, okafor, nih, "2026-01", "2026-03", 60)
    insert_allocation(db, None, okafor, doe, "2026-01", "2026-03", 40)
    insert_allocation(db, None, okafor, nih, "2026-04", "2026-07", 100)
    insert_allocation(db, None, nair, nih, "2026-02", "2026-07", 50)
    insert_allocation(db, None, nair, sloan, "2026-02", "2026-07", 50)
    insert_allocation(db, None, wilson, sloan, "2026-01", "2026-06", 100)
    insert_allocation(db, None, tanaka, nih, "2026-01", "2026-07", 30)

    insert_transaction(db, nsf, "2025-11-15", 45_000, "Lab equipment - confocal microscope")
    insert_transaction(db, nsf, "2026-04-02", 2_200, "Conference travel - M. Chen (SPIE)")
    insert_transaction(db, nih, "2026-01-20", 18_500, "Sequencing reagents")
    insert_transaction(db, nih, "2026-05-10", 9_800, "Core facility fees")
    insert_transaction(db, doe, "2025-06-01", 3_200, "Workshop materials")
    insert_transaction(db, sloan, "2026-02-14", 1_500, "Travel - S. Wilson (poster session)")

    # A what-if scenario: what if Yuki's NIH effort went from 30% to 60%?
    cur = db.execute(
        "INSERT INTO scenarios (name, created_at) VALUES (?, ?)",
        ("What if: bump Yuki to 60% on NIH", "2026-07-01T09:00:00"),
    )
    scenario_id = cur.lastrowid
    db.execute(
        """INSERT INTO allocations (scenario_id, student_id, grant_id, month, percent)
           SELECT ?, student_id, grant_id, month, percent FROM allocations WHERE scenario_id IS NULL""",
        (scenario_id,),
    )
    db.execute(
        "DELETE FROM allocations WHERE scenario_id = ? AND student_id = ? AND grant_id = ?",
        (scenario_id, tanaka, nih),
    )
    insert_allocation(db, scenario_id, tanaka, nih, "2026-01", "2026-07", 60)

    db.commit()
    db.close()
    print(f"Seeded {path}")


def seed_alex_rivera():
    db, path = fresh_db(slugify("Dr. Alex Rivera"))

    physics = insert_department(db, "Physics", stipend_dollars=3600, tuition_dollars=1150, fringe_rate_percent=29)

    nsf_physics = insert_grant(db, "NSF Physics Frontiers", "NSF", 300_000, 48, "2025-06-01", "2028-05-31")
    templeton = insert_grant(db, "Templeton Foundation Grant", "John Templeton Foundation", 120_000, 10, "2024-01-01", "2026-06-30")

    petrov = insert_student(db, "Elena Petrov", "epetrov@university.edu", physics, 3700, start_date="2023-09-01")
    webb = insert_student(db, "Marcus Webb", "mwebb@university.edu", physics, 3500, role="postdoc",
                           start_date="2025-06-01")

    insert_allocation(db, None, petrov, nsf_physics, "2026-01", "2026-12", 100)
    insert_allocation(db, None, webb, templeton, "2026-01", "2026-06", 100)
    insert_allocation(db, None, webb, nsf_physics, "2026-07", "2026-07", 100)

    insert_transaction(db, nsf_physics, "2026-03-10", 12_000, "Lab supplies - laser equipment")
    insert_transaction(db, templeton, "2025-09-05", 2_500, "Workshop travel")

    db.commit()
    db.close()
    print(f"Seeded {path}")


if __name__ == "__main__":
    seed_maria_santos()
    seed_alex_rivera()
