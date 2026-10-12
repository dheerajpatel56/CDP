"""Regression suite for the compiler.

Each case states the question, whether it should compile at all, and fragments
that must appear in the generated statement. Every compiling case is also
executed, so a statement that parses but the database rejects still fails.

    python -m tests.test_compiler
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compiler.pipeline import QueryCompiler          # noqa: E402
from db.executor import ExecutionError, execute      # noqa: E402

# (question, should_compile, fragments required in the raw SQL)
CASES = [
    # --- shape of the original worked example ---------------------------
    ("Show the top 5 students from each department who scored above 85", True,
     ["ROW_NUMBER", "PARTITION BY", "rank_in_group <= 5", "students.marks > ?"]),

    # --- filters --------------------------------------------------------
    ("List students who scored above 90", True, ["students.marks > ?"]),
    ("Find students from Mumbai with marks between 70 and 90", True,
     ["students.city = ?", ">= ?", "<= ?"]),
    ("students from Mumbai or Delhi", True, ["OR"]),
    ("students with marks above 90 and age under 20", True,
     ["students.marks > ?", "AND", "students.age < ?"]),
    ("students in Computer Science", True, ["departments.name = ?"]),

    # --- negation (silently inverted before this was fixed) -------------
    ("students not from Mumbai", True, ["NOT (students.city = ?)"]),

    # --- dates ----------------------------------------------------------
    ("students admitted in 2023", True, ["strftime", "= ?"]),
    ("students who joined after 2022", True, ["strftime", "> ?"]),
    ("students admitted last year", True, ["strftime"]),
    ("students admitted between 2022 and 2023", True, ["strftime", ">= ?", "<= ?"]),

    # --- column against column -----------------------------------------
    ("students whose marks are greater than age", True,
     ["students.marks > students.age"]),

    # --- grouping and aggregates ---------------------------------------
    ("What is the average marks of students in each department", True,
     ["AVG(students.marks)", "GROUP BY departments.name"]),
    ("Count students in each city", True, ["COUNT(*)", "GROUP BY students.city"]),
    ("Show departments with average marks greater than 70", True, ["HAVING AVG"]),
    ("departments with more than 20 students", True, ["HAVING COUNT(*) > ?"]),
    ("cities with at least 15 students", True, ["HAVING COUNT(*) >= ?"]),
    ("how many students are there", True, ["COUNT(*)"]),

    # --- ordering, limits, distinct ------------------------------------
    ("Show the top 10 students sorted by marks descending", True,
     ["ORDER BY students.marks DESC", "LIMIT ?"]),
    ("youngest 5 students", True, ["ORDER BY students.age ASC", "LIMIT ?"]),
    ("list distinct cities", True, ["SELECT DISTINCT"]),

    # --- refused: this compiler has no production for destructive verbs --
    ("drop table students", False, []),
    ("delete all students", False, []),
    ("update students set marks to 100", False, []),

    # --- refused: nothing resolvable in the schema ----------------------
    ("what is the weather today", False, []),
]


def run():
    compiler = QueryCompiler()
    failures = []

    for question, should_compile, fragments in CASES:
        result = compiler.compile(question)
        problems = []

        if result.ok != should_compile:
            want = "compile" if should_compile else "be refused"
            got = "compiled" if result.ok else (
                "refused in %s: %s" % (result.failed_phase, result.errors[-1]["message"])
            )
            problems.append("expected it to %s, but it %s" % (want, got))
        elif result.ok:
            sql = " ".join(result.sql.split())
            for fragment in fragments:
                if fragment not in sql:
                    problems.append("missing %r in: %s" % (fragment, sql))
            try:
                execute(result.sql, result.params)
            except ExecutionError as e:
                problems.append("database rejected the statement: %s" % e)

        if problems:
            failures.append((question, problems))

    for question, problems in failures:
        print("FAIL  %r" % question)
        for p in problems:
            print("        %s" % p)

    passed = len(CASES) - len(failures)
    print("\n%d passed, %d failed, %d total" % (passed, len(failures), len(CASES)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
