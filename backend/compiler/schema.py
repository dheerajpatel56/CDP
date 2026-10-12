"""Schema catalog — the compiler's symbol table."""
from dataclasses import dataclass, field


@dataclass
class Column:
    name: str
    type: str            # int | float | text | date
    synonyms: list = field(default_factory=list)


@dataclass
class Table:
    name: str
    columns: list
    synonyms: list = field(default_factory=list)

    def column(self, name):
        for c in self.columns:
            if c.name == name:
                return c
        return None


@dataclass
class ForeignKey:
    from_table: str
    from_column: str
    to_table: str
    to_column: str


class Schema:
    """Symbol table + join graph used by semantic analysis and codegen."""

    MAX_DISTINCT = 60   # only low-cardinality columns enter the value index

    def __init__(self, tables, foreign_keys):
        self.tables = {t.name: t for t in tables}
        self.foreign_keys = foreign_keys
        self.value_index = {}   # lowercase value -> (table, column, original)

    def build_value_index(self, conn):
        """Catalog statistics pass.

        Samples distinct values of low-cardinality text columns so the lexer can
        resolve a bare literal ("Mumbai") to the column that holds it
        (students.city) instead of discarding it as an unknown word.
        """
        self.value_index = {}
        for table in self.tables.values():
            for col in table.columns:
                if col.type != "text":
                    continue
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT DISTINCT %s FROM %s LIMIT %d"
                                % (col.name, table.name, self.MAX_DISTINCT + 1))
                    rows = cur.fetchall()
                except Exception:
                    continue
                if len(rows) > self.MAX_DISTINCT:
                    continue
                for row in rows:
                    # drivers differ: a row may arrive as a tuple or as a mapping
                    val = next(iter(row.values())) if isinstance(row, dict) else row[0]
                    if val is None:
                        continue
                    key = str(val).lower()
                    self.value_index.setdefault(key, (table.name, col.name, val))
        return len(self.value_index)

    def resolve_value(self, word):
        return self.value_index.get(word.lower())

    # --- lookup helpers -------------------------------------------------
    def resolve_table(self, word):
        word = word.lower()
        for t in self.tables.values():
            if word == t.name or word in t.synonyms:
                return t.name
        return None

    def resolve_column(self, word, table=None):
        """Return (table, column) or None. Ambiguity resolved by `table` hint."""
        word = word.lower()
        hits = []
        for t in self.tables.values():
            if table and t.name != table:
                continue
            for c in t.columns:
                if word == c.name or word in c.synonyms:
                    hits.append((t.name, c.name))
        if not hits:
            return None
        return hits[0]

    def join_path(self, a, b):
        """Direct FK edge between two tables, or None."""
        for fk in self.foreign_keys:
            if {fk.from_table, fk.to_table} == {a, b}:
                return fk
        return None


DEMO_SCHEMA = Schema(
    tables=[
        Table("students", [
            Column("id", "int", ["student id", "roll", "roll number"]),
            Column("name", "text", ["student name", "names"]),
            Column("department_id", "int", ["dept id"]),
            Column("marks", "float", ["score", "scores", "scored", "mark", "grade", "percentage"]),
            Column("age", "int", ["ages"]),
            Column("city", "text", ["cities", "hometown"]),
            Column("admission_date", "date", ["joined", "admitted"]),
        ], synonyms=["student", "pupils", "learners"]),
        Table("departments", [
            Column("id", "int", ["dept id"]),
            Column("name", "text", ["department name", "dept name", "dept"]),
            Column("building", "text", ["block"]),
        ], synonyms=["department", "depts", "dept"]),
        Table("courses", [
            Column("id", "int", []),
            Column("title", "text", ["course", "course name", "subject"]),
            Column("department_id", "int", ["dept id"]),
            Column("credits", "int", ["credit"]),
        ], synonyms=["course", "subjects"]),
        Table("enrollments", [
            Column("id", "int", []),
            Column("student_id", "int", []),
            Column("course_id", "int", []),
            Column("grade", "float", ["grades"]),
        ], synonyms=["enrollment", "registrations"]),
    ],
    foreign_keys=[
        ForeignKey("students", "department_id", "departments", "id"),
        ForeignKey("courses", "department_id", "departments", "id"),
        ForeignKey("enrollments", "student_id", "students", "id"),
        ForeignKey("enrollments", "course_id", "courses", "id"),
    ],
)
