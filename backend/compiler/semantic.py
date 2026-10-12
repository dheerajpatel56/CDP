"""Phase 3 - Semantic analysis.

Walks the AST against the schema symbol table and checks the things syntax
cannot: do these tables and columns exist, are the comparison operand types
compatible, is every joined table reachable through a foreign key, and is an
aggregate used without a legal grouping. Produces a resolved join plan that
code generation consumes.
"""
from .ast_nodes import (Aggregate, BoolOp, ColumnRef, Comparison, Extract,
                        Literal, NotOp)

NUMERIC = ("int", "float")

# operator -> operand types it accepts
OP_TYPES = {
    ">": NUMERIC + ("date",), "<": NUMERIC + ("date",),
    ">=": NUMERIC + ("date",), "<=": NUMERIC + ("date",),
    "=": NUMERIC + ("text", "date"), "!=": NUMERIC + ("text", "date"),
}

AGG_TYPES = {
    "AVG": NUMERIC, "SUM": NUMERIC,
    "MAX": NUMERIC + ("date", "text"), "MIN": NUMERIC + ("date", "text"),
    "COUNT": NUMERIC + ("text", "date"),
}


class SemanticError(Exception):
    pass


class JoinStep:
    """One resolved FK edge in the join plan."""

    def __init__(self, left, right, left_col, right_col):
        self.left = left
        self.right = right
        self.left_col = left_col
        self.right_col = right_col

    def to_dict(self):
        return {
            "left": self.left, "right": self.right,
            "on": "%s.%s = %s.%s" % (self.left, self.left_col,
                                     self.right, self.right_col),
        }


class SemanticAnalyzer:
    def __init__(self, schema):
        self.schema = schema
        self.errors = []
        self.warnings = []

    def analyze(self, query):
        self.errors = []
        self.warnings = []

        self._check_table(query.source)
        for t in query.joins:
            self._check_table(t)

        join_plan = self._resolve_joins(query)

        for p in query.projections:
            self._check_expr(p)
        self._check_predicate(query.where, "WHERE")
        self._check_predicate(query.having, "HAVING")
        for g in query.group_by + query.partition_by:
            self._check_expr(g)
        for o in query.order_by:
            self._check_expr(o.target)

        self._check_grouping(query)
        self._check_limit(query)

        if self.errors:
            raise SemanticError("; ".join(e["message"] for e in self.errors))

        return {
            "join_plan": [j.to_dict() for j in join_plan],
            "tables": [query.source] + query.joins,
            "warnings": self.warnings,
            "resolved_types": self._type_map(query),
        }, join_plan

    # --- checks ----------------------------------------------------------
    def _check_table(self, name):
        if name not in self.schema.tables:
            self.error("unknown table '%s'" % name)

    def _column_type(self, ref):
        tbl = self.schema.tables.get(ref.table)
        if tbl is None:
            self.error("unknown table '%s'" % ref.table)
            return None
        col = tbl.column(ref.column)
        if col is None:
            self.error("column '%s' does not exist on table '%s'"
                       % (ref.column, ref.table))
            return None
        return col.type

    def _check_expr(self, node):
        if isinstance(node, ColumnRef):
            return self._column_type(node)
        if isinstance(node, Extract):
            t = self._check_expr(node.source)
            if t and t != "date":
                self.error("cannot take the %s of a %s column" % (node.part, t))
            return "int"
        if isinstance(node, Literal):
            if isinstance(node.value, bool):
                return "int"
            if isinstance(node.value, int):
                return "int"
            if isinstance(node.value, float):
                return "float"
            return "text"
        if isinstance(node, Aggregate):
            if node.target is None:
                if node.func != "COUNT":
                    self.error("%s requires a column to aggregate" % node.func)
                return "int"
            t = self._column_type(node.target)
            if t and t not in AGG_TYPES[node.func]:
                self.error("%s cannot be applied to %s column '%s'"
                           % (node.func, t, node.target.column))
            return "float" if node.func in ("AVG", "SUM") else t
        return None

    def _check_predicate(self, node, clause):
        if node is None:
            return
        if isinstance(node, Comparison):
            self._coerce_year(node)
            lt = self._check_expr(node.left)
            rt = self._check_expr(node.right)
            if isinstance(node.right, Literal) and node.right.value is None:
                self.error("%s clause has a comparison with no value" % clause)
                return
            allowed = OP_TYPES.get(node.op, ())
            if lt and lt not in allowed:
                self.error("operator '%s' cannot be applied to %s column '%s'"
                           % (node.op, lt, getattr(node.left, "column", "?")))
            if lt and rt and not self._compatible(lt, rt):
                self.error("type mismatch in %s: %s %s %s" % (clause, lt, node.op, rt))
        elif isinstance(node, BoolOp):
            for o in node.operands:
                self._check_predicate(o, clause)
        elif isinstance(node, NotOp):
            self._check_predicate(node.operand, clause)

    def _coerce_year(self, node):
        """A date column compared to a bare year is a comparison of year parts.

        "admitted in 2023" means the year of admission_date, not the whole date,
        so the column reference is rewritten to its year component in place.
        """
        if not isinstance(node.left, ColumnRef) or not isinstance(node.right, Literal):
            return
        if self._column_type(node.left) != "date":
            return
        value = node.right.value
        if isinstance(value, int) and 1900 <= value <= 2100:
            node.left = Extract("year", node.left)
            self.warn("'%s' read as a year, comparing the year part of %s"
                      % (value, node.left.source.column))

    @staticmethod
    def _compatible(a, b):
        if a in NUMERIC and b in NUMERIC:
            return True
        return a == b

    def _check_grouping(self, query):
        """Aggregate mixed with bare columns requires a GROUP BY."""
        has_agg = any(isinstance(p, Aggregate) for p in query.projections)
        bare = [p for p in query.projections if isinstance(p, ColumnRef)]
        if has_agg and bare and not query.group_by:
            # recoverable: group by every bare projected column
            query.group_by = list(bare)
            self.warn("aggregate mixed with plain columns - grouping by %s"
                      % ", ".join("%s.%s" % (c.table, c.column) for c in bare))
        if query.having is not None and not query.group_by:
            # HAVING is only legal over a grouping - group by the plain columns
            keys = [p for p in query.projections if isinstance(p, ColumnRef)]
            if keys:
                query.group_by = list(keys)
                self.warn("HAVING requires a grouping - grouping by %s"
                          % ", ".join("%s.%s" % (c.table, c.column) for c in keys))
            else:
                self.error("HAVING clause with nothing to group by")

    def _check_limit(self, query):
        if query.limit is not None and query.limit <= 0:
            self.error("limit must be a positive number, got %s" % query.limit)

    # --- join resolution -------------------------------------------------
    def _resolve_joins(self, query):
        """Connect every referenced table to the source via FK edges (BFS)."""
        plan = []
        connected = {query.source}
        pending = [t for t in query.joins if t != query.source]

        progress = True
        while pending and progress:
            progress = False
            for t in list(pending):
                step = self._find_edge(connected, t)
                if step:
                    plan.append(step)
                    connected.add(t)
                    pending.remove(t)
                    progress = True

        for t in pending:
            step = self._find_bridge(connected, t)
            if step:
                plan.extend(step)
                connected.add(t)
                for s in step:
                    connected.add(s.right)
            else:
                self.error("no foreign-key path connects '%s' to '%s'"
                           % (t, query.source))
        return plan

    def _find_edge(self, connected, target):
        for fk in self.schema.foreign_keys:
            if fk.from_table in connected and fk.to_table == target:
                return JoinStep(fk.from_table, fk.to_table, fk.from_column, fk.to_column)
            if fk.to_table in connected and fk.from_table == target:
                return JoinStep(fk.to_table, fk.from_table, fk.to_column, fk.from_column)
        return None

    def _find_bridge(self, connected, target):
        """Two-hop path through an intermediate table (e.g. via enrollments)."""
        for mid in self.schema.tables:
            if mid in connected:
                continue
            first = self._find_edge(connected, mid)
            if not first:
                continue
            second = self._find_edge(connected | {mid}, target)
            if second:
                self.warn("joining '%s' through intermediate table '%s'" % (target, mid))
                return [first, second]
        return None

    # --- reporting -------------------------------------------------------
    def _type_map(self, query):
        out = {}
        for ref in self._all_refs(query):
            t = self.schema.tables.get(ref.table)
            if t and t.column(ref.column):
                out["%s.%s" % (ref.table, ref.column)] = t.column(ref.column).type
        return out

    def _all_refs(self, query):
        refs = []

        def walk(n):
            if isinstance(n, ColumnRef):
                refs.append(n)
            elif isinstance(n, Extract):
                walk(n.source)
            elif isinstance(n, Aggregate) and n.target:
                refs.append(n.target)
            elif isinstance(n, Comparison):
                walk(n.left)
                walk(n.right)
            elif isinstance(n, BoolOp):
                for o in n.operands:
                    walk(o)
            elif isinstance(n, NotOp):
                walk(n.operand)

        for p in query.projections:
            walk(p)
        walk(query.where)
        walk(query.having)
        for g in query.group_by + query.partition_by:
            walk(g)
        for o in query.order_by:
            walk(o.target)
        return refs

    def error(self, msg):
        self.errors.append({"severity": "error", "message": msg})

    def warn(self, msg):
        self.warnings.append({"severity": "warning", "message": msg})
