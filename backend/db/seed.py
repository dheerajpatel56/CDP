"""Demo database. SQLite so the project runs with no external service.

Swap DB_PATH for a PostgreSQL DSN later - the compiler emits standard SQL and
the window function used by "top N per group" works on both engines.
"""
import os
import random
import sqlite3

from .config import ACTIVE

DB_PATH = os.path.join(os.path.dirname(__file__), "demo.db")

SCHEMA_SQL = """
DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS departments;

CREATE TABLE departments (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    building TEXT
);

CREATE TABLE students (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    department_id  INTEGER REFERENCES departments(id),
    marks          REAL,
    age            INTEGER,
    city           TEXT,
    admission_date TEXT
);

CREATE TABLE courses (
    id            INTEGER PRIMARY KEY,
    title         TEXT NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    credits       INTEGER
);

CREATE TABLE enrollments (
    id         INTEGER PRIMARY KEY,
    student_id INTEGER REFERENCES students(id),
    course_id  INTEGER REFERENCES courses(id),
    grade      REAL
);

CREATE INDEX idx_students_dept  ON students(department_id);
CREATE INDEX idx_students_marks ON students(marks);
CREATE INDEX idx_enroll_student ON enrollments(student_id);
"""

# Same shape, PostgreSQL types. admission_date is a real DATE here, which is why
# code generation emits EXTRACT rather than strftime against this backend.
SCHEMA_SQL_PG = """
DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS departments;

CREATE TABLE departments (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    building TEXT
);

CREATE TABLE students (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    department_id  INTEGER REFERENCES departments(id),
    marks          REAL,
    age            INTEGER,
    city           TEXT,
    admission_date DATE
);

CREATE TABLE courses (
    id            INTEGER PRIMARY KEY,
    title         TEXT NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    credits       INTEGER
);

CREATE TABLE enrollments (
    id         INTEGER PRIMARY KEY,
    student_id INTEGER REFERENCES students(id),
    course_id  INTEGER REFERENCES courses(id),
    grade      REAL
);

CREATE INDEX idx_students_dept  ON students(department_id);
CREATE INDEX idx_students_marks ON students(marks);
CREATE INDEX idx_enroll_student ON enrollments(student_id);
"""

DEPARTMENTS = [
    (1, "Computer Science", "Block A"),
    (2, "Mechanical", "Block B"),
    (3, "Electrical", "Block C"),
    (4, "Civil", "Block D"),
    (5, "Electronics", "Block E"),
]

COURSES = [
    (1, "Compiler Design", 1, 4), (2, "Operating Systems", 1, 4),
    (3, "Data Structures", 1, 3), (4, "Thermodynamics", 2, 4),
    (5, "Fluid Mechanics", 2, 3), (6, "Circuit Theory", 3, 4),
    (7, "Power Systems", 3, 3), (8, "Structural Analysis", 4, 4),
    (9, "Signals and Systems", 5, 4), (10, "VLSI Design", 5, 3),
]

FIRST = ["Aarav", "Diya", "Rohan", "Isha", "Kabir", "Ananya", "Vivaan", "Meera",
         "Arjun", "Sara", "Dhruv", "Nisha", "Karan", "Priya", "Aditya", "Riya",
         "Nikhil", "Tara", "Veer", "Simran"]
LAST = ["Sharma", "Patel", "Nair", "Reddy", "Iyer", "Gupta", "Mehta", "Singh",
        "Bose", "Kulkarni"]
CITIES = ["Mumbai", "Delhi", "Bengaluru", "Pune", "Chennai", "Hyderabad",
          "Kolkata", "Ahmedabad"]


def generate_students(n=120, seed=42):
    rng = random.Random(seed)
    rows = []
    for i in range(1, n + 1):
        name = "%s %s" % (rng.choice(FIRST), rng.choice(LAST))
        dept = rng.randint(1, len(DEPARTMENTS))
        marks = round(min(100.0, max(35.0, rng.gauss(72, 14))), 1)
        age = rng.randint(18, 24)
        city = rng.choice(CITIES)
        year = rng.choice([2022, 2023, 2024, 2025, 2026])
        date = "%d-%02d-%02d" % (year, rng.randint(6, 8), rng.randint(1, 28))
        rows.append((i, name, dept, marks, age, city, date))
    return rows


def generate_enrollments(students, seed=7):
    rng = random.Random(seed)
    rows = []
    eid = 1
    for s in students:
        dept_courses = [c for c in COURSES if c[2] == s[2]]
        for course in rng.sample(dept_courses, k=min(2, len(dept_courses))):
            rows.append((eid, s[0], course[0], round(min(100.0, max(30.0, rng.gauss(70, 15))), 1)))
            eid += 1
    return rows


TABLES = ("departments", "courses", "students", "enrollments")


def build(path=DB_PATH):
    """Create and populate the SQLite demo database."""
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL)
    students = generate_students()
    conn.executemany("INSERT INTO departments VALUES (?,?,?)", DEPARTMENTS)
    conn.executemany("INSERT INTO courses VALUES (?,?,?,?)", COURSES)
    conn.executemany("INSERT INTO students VALUES (?,?,?,?,?,?,?)", students)
    conn.executemany("INSERT INTO enrollments VALUES (?,?,?,?)",
                     generate_enrollments(students))
    conn.commit()
    counts = {t: conn.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
              for t in TABLES}
    conn.close()
    return counts


def build_postgres(url):
    """Create and populate the same demo data in PostgreSQL."""
    import datetime

    import psycopg

    students = generate_students()
    # the PG column is a real DATE, so hand it date objects rather than strings
    students_pg = [
        (i, name, dept, marks, age, city,
         datetime.date.fromisoformat(admitted))
        for (i, name, dept, marks, age, city, admitted) in students
    ]

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL_PG)
            cur.executemany("INSERT INTO departments VALUES (%s,%s,%s)", DEPARTMENTS)
            cur.executemany("INSERT INTO courses VALUES (%s,%s,%s,%s)", COURSES)
            cur.executemany(
                "INSERT INTO students VALUES (%s,%s,%s,%s,%s,%s,%s)", students_pg)
            cur.executemany("INSERT INTO enrollments VALUES (%s,%s,%s,%s)",
                            generate_enrollments(students))
        conn.commit()
        counts = {}
        with conn.cursor() as cur:
            for t in TABLES:
                cur.execute("SELECT COUNT(*) FROM %s" % t)
                counts[t] = cur.fetchone()[0]
    return counts


if __name__ == "__main__":
    if ACTIVE.is_postgres:
        print("building PostgreSQL schema")
        counts = build_postgres(ACTIVE.url)
    else:
        print("built %s" % DB_PATH)
        counts = build()
    for table, n in counts.items():
        print("  %-12s %4d rows" % (table, n))
