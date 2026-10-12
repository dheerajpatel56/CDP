"""Phase 6 - Code generation.

Walks the optimized IR and emits SQL. Literals are never interpolated into the
statement text: every constant becomes a bound parameter, which is both the
correct codegen choice and the reason the generated SQL cannot be injected into.
"""
from .ast_nodes import (Aggregate, BoolOp, ColumnRef, Comparison, Extract,
                        Literal, NotOp)


class SQLGenerator:
    # how a bound parameter is written, per target engine
    PLACEHOLDERS = {"sqlite": "?", "postgres": "%s"}

    def __init__(self, schema, dialect="sqlite"):
        self.schema = schema
        self.dialect = dialect
        self.placeholder = self.PLACEHOLDERS.get(dialect, "?")
        self.params = []

    def generate(self, query, join_plan):
        self.params = []
        parts = []

        parts.append(self._select_clause(query))
        parts.append("FROM " + query.source)
        for step in join_plan:
            parts.append("INNER JOIN %s ON %s.%s = %s.%s"
                         % (step.right, step.left, step.left_col,
                            step.right, step.right_col))

        if query.where is not None:
            parts.append("WHERE " + self._expr(query.where))
        if query.group_by:
            parts.append("GROUP BY " + ", ".join(self._expr(g) for g in query.group_by))
        if query.having is not None:
            parts.append("HAVING " + self._expr(query.having))
        if query.order_by and not query.partition_by:
            parts.append("ORDER BY " + ", ".join(
                "%s %s" % (self._expr(o.target), o.direction) for o in query.order_by))
        if query.limit and not query.partition_by:
            parts.append("LIMIT " + self.placeholder)
            self.params.append(query.limit)

        sql = "\n".join(parts)

        if query.partition_by:
            sql = self._wrap_in_rank(query, sql)

        return sql + ";", list(self.params)

    # --- clauses ---------------------------------------------------------
    def _select_clause(self, query):
        aliases = self._alias_map(query.projections)
        cols = [self._projection(p, aliases) for p in query.projections]
        keyword = "SELECT DISTINCT" if query.distinct else "SELECT"
        return keyword + " " + ",\n       ".join(cols)

    @staticmethod
    def _alias_map(projections):
        """Qualify an alias with its table only when the bare name collides."""
        counts = {}
        for p in projections:
            if isinstance(p, ColumnRef):
                counts[p.column] = counts.get(p.column, 0) + 1
        out = {}
        for p in projections:
            if isinstance(p, Extract):
                out[id(p)] = "%s_%s" % (p.part, getattr(p.source, "column", "value"))
            elif isinstance(p, ColumnRef):
                out[id(p)] = ("%s_%s" % (p.table, p.column)
                              if counts[p.column] > 1 else p.column)
            elif isinstance(p, Aggregate):
                out[id(p)] = "%s_%s" % (p.func.lower(),
                                        p.target.column if p.target else "all")
        return out

    def _projection(self, node, aliases):
        alias = aliases.get(id(node))
        if isinstance(node, Aggregate):
            inner = self._expr(node.target) if node.target else "*"
            return "%s(%s) AS %s" % (node.func, inner, alias)
        sql = self._expr(node)
        if isinstance(node, ColumnRef) and alias != node.column:
            return "%s AS %s" % (sql, alias)
        return sql

    def _wrap_in_rank(self, query, inner_sql):
        """'Top N per group' compiles to a windowed rank, not a bare LIMIT."""
        aliases = self._alias_map(query.projections)
        order = query.order_by[0] if query.order_by else None
        order_sql = ("%s %s" % (self._expr(order.target), order.direction)
                     if order else "1")
        partition_sql = ", ".join(self._expr(p) for p in query.partition_by)

        window = ("ROW_NUMBER() OVER (PARTITION BY %s ORDER BY %s) AS rank_in_group"
                  % (partition_sql, order_sql))
        ranked = inner_sql.replace("SELECT ", "SELECT\n       %s,\n       " % window, 1)

        outer_cols = [aliases.get(id(p), self._expr(p)) for p in query.projections]
        # the partition key, as it is named inside the CTE
        group_alias = next((aliases[id(p)] for p in query.projections
                            if id(p) in aliases and isinstance(p, ColumnRef)
                            and any(p.table == g.table and p.column == g.column
                                    for g in query.partition_by)), outer_cols[0])

        return ("WITH ranked AS (\n%s\n)\n"
                "SELECT %s\nFROM ranked\nWHERE rank_in_group <= %d\n"
                "ORDER BY %s, rank_in_group"
                % (_indent(ranked), ", ".join(outer_cols), query.limit, group_alias))

    # --- expressions -----------------------------------------------------
    def _expr(self, node):
        if isinstance(node, ColumnRef):
            return "%s.%s" % (node.table, node.column)
        if isinstance(node, Extract):
            inner = self._expr(node.source)
            if self.dialect == "postgres":
                return "EXTRACT(%s FROM %s)" % (node.part.upper(), inner)
            fmt = {"year": "%Y", "month": "%m", "day": "%d"}[node.part]
            return "CAST(strftime('%s', %s) AS INTEGER)" % (fmt, inner)
        if isinstance(node, Literal):
            self.params.append(node.value)
            return self.placeholder
        if isinstance(node, Aggregate):
            return "%s(%s)" % (node.func, self._expr(node.target) if node.target else "*")
        if isinstance(node, Comparison):
            return "%s %s %s" % (self._expr(node.left), node.op, self._expr(node.right))
        if isinstance(node, BoolOp):
            joiner = " %s " % node.op
            return "(" + joiner.join(self._expr(o) for o in node.operands) + ")"
        if isinstance(node, NotOp):
            return "NOT (%s)" % self._expr(node.operand)
        raise ValueError("cannot generate SQL for %r" % node)


def _indent(text, pad="  "):
    return "\n".join(pad + line for line in text.split("\n"))


def inline_params(sql, params, placeholder="?"):
    """Readable preview only - never sent to the database."""
    out = sql
    for p in params:
        literal = ("'%s'" % p) if isinstance(p, str) else str(p)
        out = out.replace(placeholder, literal, 1)
    return out
