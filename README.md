# Natural Language Query Compiler

An intelligent framework for query generation, optimization, and analysis.
Natural language goes in, verified and optimized SQL comes out — through the
same phase structure as a classical compiler.

## Compiler phases

| Phase | Module | Compiler concept |
|---|---|---|
| 1. Lexical analysis | `compiler/lexer.py` | Tokenization (maximal munch) |
| 2. Syntax analysis | `compiler/parser.py` | Recursive-descent parsing → AST |
| 3. Semantic analysis | `compiler/semantic.py` | Symbol table, type checking, join resolution |
| 4. Intermediate representation | `compiler/ir.py` | Three-address relational algebra |
| 5. Optimization | `compiler/optimizer.py` | 7 rewrite passes |
| 6. Code generation | `compiler/codegen.py` | Target code (SQL) emission |
| 7. Security analysis | `compiler/security.py` | Static analysis / safety gate |
| 8. Runtime | `db/executor.py` | Execution + `EXPLAIN QUERY PLAN` |

The catalog pass in `Schema.build_value_index` samples low-cardinality columns
so a bare literal (`Mumbai`) resolves to the column that holds it
(`students.city`) instead of being discarded as an unknown word.

### Optimization passes

constant folding · predicate pushdown · filter merging · projection pruning ·
join reordering · limit pushdown · dead code elimination

Every rewrite is recorded, so the before/after plan can be shown side by side.

## Running it

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m db.seed
```

CLI, with every phase printed:

```bash
python cli.py --stages "Show the top 5 students from each department who scored above 85"
```

Interactive REPL:

```bash
python cli.py
```

API:

```bash
.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
```

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Status, phase list, row counts |
| `GET /api/schema` | Tables, columns, foreign keys |
| `GET /api/examples` | Sample questions |
| `POST /api/compile` | Full phase-by-phase compilation + results |
| `POST /api/explain` | Plan and SQL only, no execution |

Interactive docs at `http://localhost:8000/docs`.

## Worked example

Input:

> Show the top 5 students from each department who scored above 85

Optimized IR:

```
t0 = SCAN students   COLUMNS [department_id, marks, name]
t1 = SCAN departments COLUMNS [id, name]
t3 = FILTER t0 PREDICATE students.marks > 85
t2 = JOIN t3, t1 ON students.department_id = departments.id
t4 = RANK t2 PARTITION BY [departments.name] ORDER BY students.marks DESC
t5 = FILTER t4 PREDICATE rank <= 5
t6 = PROJECT t5 COLUMNS [departments.name, students.name, students.marks]
```

The filter moved below the join, so fewer rows ever reach it. Generated SQL:

```sql
WITH ranked AS (
  SELECT
         ROW_NUMBER() OVER (PARTITION BY departments.name
                            ORDER BY students.marks DESC) AS rank_in_group,
         departments.name AS departments_name,
         students.name    AS students_name,
         students.marks
  FROM students
  INNER JOIN departments ON students.department_id = departments.id
  WHERE students.marks > ?
)
SELECT departments_name, students_name, marks
FROM ranked
WHERE rank_in_group <= 5
ORDER BY departments_name, rank_in_group;
```

`"top N per group"` compiles to a window function, not a `LIMIT` — a plain
`LIMIT 5` would return five rows total rather than five per department.

## What it understands

| Pattern | Example | Compiles to |
|---|---|---|
| Comparison | `students who scored above 90` | `marks > ?` |
| Range | `marks between 70 and 90` | `>= ? AND <= ?` |
| Catalog value | `students from Mumbai` | `city = ?`, resolved by the value index |
| Negation | `students not from Mumbai` | `NOT (city = ?)` |
| Boolean mix | `marks above 90 and age under 20` | `AND` / `OR` tree |
| Year | `students admitted in 2023` | year part of the date column |
| Relative year | `students admitted last year` | the concrete year, bound at compile time |
| Temporal compare | `students who joined after 2022` | `year > ?` |
| Column vs column | `marks greater than age` | `marks > age` |
| Grouped aggregate | `average marks in each department` | `AVG` with `GROUP BY` |
| Count threshold | `departments with more than 20 students` | `HAVING COUNT(*) > ?` |
| Top N per group | `top 5 students from each department` | windowed rank |
| Superlative | `youngest 5 students` | `ORDER BY age ASC LIMIT ?` |
| Distinct | `list distinct cities` | `SELECT DISTINCT` |

Destructive verbs (`drop`, `delete`, `update`, `truncate`) are refused in syntax
analysis: there is no production that translates them.

## Tests

```bash
cd backend
.venv/Scripts/python.exe -m tests.test_compiler
```

25 cases covering each pattern above plus the refusals. Every case that compiles
is also executed, so a statement the database rejects fails the suite.

## Security model

Codegen never interpolates a literal into the statement; every constant is a
bound parameter. Phase 7 then verifies the result before execution:

- statement must be `SELECT` / `WITH`
- no DDL or DML verb anywhere in the output
- no comment markers, stacked statements, tautologies, `UNION` injection, or
  metadata-table access
- every referenced table is on the authorized list
- join count and row count are capped; the runtime connection is read-only

Requests like `drop table students` are rejected in syntax analysis — the
compiler has no production that translates a destructive verb.

## Database

SQLite by default, so the project runs with no external service
(`db/seed.py` generates 5 departments, 10 courses, 120 students, and their
enrollments).

### Switching to PostgreSQL

```bash
cd backend
cp .env.example .env        # then put your password in .env
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe setup_postgres.py
```

`setup_postgres.py` creates the database if needed, loads the demo data, then
compiles and executes the whole test battery against PostgreSQL, so the switch
is proven rather than assumed. The running backend is reported by
`GET /api/health` and shown in the workspace header.

Only two things differ between the engines, and both are resolved in
`db/config.py` rather than scattered through the compiler:

| | SQLite | PostgreSQL |
|---|---|---|
| Bound parameter | `?` | `%s` |
| Date part | `CAST(strftime('%Y', col) AS INTEGER)` | `EXTRACT(YEAR FROM col)` |

Everything else, including the `ROW_NUMBER() OVER (PARTITION BY ...)` window
function behind "top N per group", is identical on both.

The connection string lives in `.env`, which is git-ignored, so no credential
enters the source tree.

## Frontend

A workspace that shows the compilation, not just the answer. Each of the eight
phases is a stop on the pipeline rail; selecting one shows that phase's real
artifact.

```bash
cd frontend
npm install
npm run dev
```

Run the backend on port 8000 first. Vite proxies `/api` to it.

| Phase | What the panel shows |
|---|---|
| Lexical analysis | Token stream, with schema-resolved tokens accented |
| Syntax analysis | AST as an indented listing with parser diagnostics |
| Semantic analysis | Join plan, resolved column types, recovered warnings |
| Intermediate representation | Three-address listing, one operation per line |
| Optimization | Before and after plans side by side, moved operations marked |
| Code generation | Generated SQL in Monaco, with bound parameters listed |
| Security analysis | Verdict, relations reached, per-check results |
| Execution | Result table, plus the engine's own `EXPLAIN` plan |

Stack: React, TypeScript, Tailwind, Monaco, Motion, Phosphor icons,
IBM Plex Mono and Plex Sans.

Design notes: mono-first because the content is compiler listings; the accent
marks only what the compiler resolved or rewrote, so colour carries meaning
rather than decoration; hairline rules instead of cards; motion limited to a
token-stream stagger and honoring `prefers-reduced-motion`.

## Status

Backend pipeline and frontend both complete, verified end to end against the
demo database.
